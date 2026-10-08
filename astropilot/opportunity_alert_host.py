"""Explicit foreground process host for Opportunity Alerts and optional delivery."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
import errno
import json
import os
from pathlib import Path
import signal
import sys
from threading import Event

from astropilot.opportunity_alert_notification import DisabledNotifier, MacOSNotifier, deliver_cycle
from astropilot.opportunity_alert_windows_notification import WindowsNotifier
from astropilot.opportunity_alert_ledger import FileOpportunityAlertLedger
from astropilot.opportunity_alert_scheduler import (
    OpportunityAlertScheduler, SchedulerCadence, SchedulerStatus, utc,
)
from decision.models.opportunity_alert import OpportunityAlertPolicy
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.runners.opportunity_alert_runner import OpportunityAlertRunner, OpportunityAlertCycleStatus
from decision.services.tonight_application_service import resolve_tonight_inputs


@dataclass(frozen=True, slots=True)
class HostConfig:
    cadence: SchedulerCadence
    policy: OpportunityAlertPolicy
    availability: SessionAvailability | None
    notification_channel: str = 'disabled'


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_config_key')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('nonfinite_config_number')


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('invalid_config_timestamp')
    return utc(datetime.fromisoformat(value))


def load_config(path) -> HostConfig:
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'),
            object_pairs_hook=_unique, parse_constant=_reject_constant)
        if (not isinstance(doc, dict) or not {'schema_version', 'interval_seconds', 'policy', 'availability'} <= set(doc)
                or not set(doc) <= {'schema_version', 'interval_seconds', 'policy', 'availability',
                    'notification_channel'} or type(doc['schema_version']) is not int
                or doc['schema_version'] != 1 or type(doc['interval_seconds']) is not int
                or doc['interval_seconds'] <= 0):
            raise ValueError('invalid_host_config')
        cadence = SchedulerCadence(interval=timedelta(seconds=doc['interval_seconds']))
        raw_policy = doc['policy']
        if (not isinstance(raw_policy, dict)
                or not set(raw_policy) <= {f.name for f in fields(OpportunityAlertPolicy)}):
            raise ValueError('invalid_host_policy')
        policy_values = dict(raw_policy)
        for key in ('project_keys', 'intent_ids', 'filter_profile_ids'):
            if key in policy_values:
                if not isinstance(policy_values[key], list):
                    raise ValueError('invalid_host_selectors')
                policy_values[key] = tuple(policy_values[key])
        for key in ('window_start', 'window_end'):
            if policy_values.get(key) is not None:
                policy_values[key] = _timestamp(policy_values[key])
        policy = OpportunityAlertPolicy(**policy_values)
        raw_availability = doc['availability']
        availability = None
        if raw_availability is not None:
            if (not isinstance(raw_availability, dict) or 'mode' not in raw_availability
                    or not set(raw_availability) <= {'mode', 'start', 'end', 'duration_seconds'}):
                raise ValueError('invalid_host_availability')
            values = {'mode': SessionAvailabilityMode(raw_availability['mode'])}
            for key in ('start', 'end'):
                if key in raw_availability:
                    values[key] = _timestamp(raw_availability[key])
            if 'duration_seconds' in raw_availability:
                seconds = raw_availability['duration_seconds']
                if type(seconds) is not int or seconds <= 0:
                    raise ValueError('invalid_host_duration')
                values['duration'] = timedelta(seconds=seconds)
            availability = SessionAvailability(**values)
        if policy.enabled and availability is None:
            raise ValueError('enabled_host_requires_explicit_availability')
        channel = doc.get('notification_channel', 'disabled')
        if not isinstance(channel, str) or channel not in ('disabled', 'macos', 'windows'):
            raise ValueError('invalid_notification_channel')
        return HostConfig(cadence, policy, availability, channel)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('invalid_opportunity_alert_host_config') from error


class PreparingTonightService:
    """Acquire inputs lazily, within the scheduler's reserved runner attempt."""
    def __init__(self, *, profile_provider, weather_provider, tonight_factory, availability):
        self.profile_provider = profile_provider
        self.weather_provider = weather_provider
        self.tonight_factory = tonight_factory
        self.availability = availability
        self._tonight = None

    def evaluate(self, *, reference_time_utc):
        # The production CLI helpers print prose and weather errors. The dedicated
        # serial host owns these streams and publishes only its allowlisted events.
        with open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(sink), redirect_stderr(sink):
            profile = self.profile_provider()
            inputs = resolve_tonight_inputs(profile, availability=self.availability)
            weather = self.weather_provider(inputs.location['latitude'], inputs.location['longitude'])
            if weather is None:
                # Tonight's existing forecast helper fetches again for None.
                # Stop here so a failed acquisition never causes a hidden retry.
                raise RuntimeError('host_weather_unavailable')
            if self._tonight is None:
                self._tonight = self.tonight_factory()
            return self._tonight.evaluate(profile=profile, weather=weather,
                reference_time_utc=reference_time_utc, bortle=inputs.bortle,
                equipment=inputs.equipment, availability=inputs.availability)


class HostAlreadyRunning(RuntimeError):
    """Another process owns this user-data host."""


@contextmanager
def host_lock(path):
    """Fail immediately on duplicate host; release automatically on process death."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b'\0')
                handle.flush()
            handle.seek(0)
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise HostAlreadyRunning('opportunity_alert_host_already_running') from error
            raise
        try:
            yield
        finally:
            release()


@contextmanager
def shutdown_signals(stop_event):
    previous = {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, lambda *_: stop_event.set())
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def cycle_diagnostic(result):
    return {'event': 'cycle', 'slot': result.slot.isoformat() if result.slot else None,
        'status': result.status.value, 'reason': result.reason,
        'cycle_status': result.cycle.status.value if result.cycle else None,
        'logical_time': result.cycle.logical_time.isoformat() if result.cycle and result.cycle.logical_time else None}


class OpportunityAlertHost:
    def __init__(self, *, scheduler, policy, clock, stop_event, report, wait=None, notifier=None):
        self.notifier = DisabledNotifier() if notifier is None else notifier
        self.scheduler = scheduler
        self.policy = policy
        self.clock = clock
        self.stop_event = stop_event
        self.report = report
        self.wait = stop_event.wait if wait is None else wait

    def run(self, *, once=False):
        last_slot = None
        result = None
        while not self.stop_event.is_set():
            now = utc(self.clock())
            slot = self.scheduler.cadence.slot(now)
            if last_slot is None or (slot is not None and slot > last_slot):
                result = self.scheduler.poll(policy=self.policy, now=now, cycle_time=now)
                self.report(cycle_diagnostic(result))
                delivery = deliver_cycle(result.cycle, self.notifier)
                if delivery is not None:
                    self.report({'event': 'notification', 'status': delivery.status.value,
                        'reason': delivery.reason})
                if once:
                    return result
                last_slot = slot if slot is not None else self.scheduler.cadence.anchor - self.scheduler.cadence.interval
                continue
            next_due = self.scheduler.cadence.anchor if slot is None else last_slot + self.scheduler.cadence.interval
            delay = (next_due - now).total_seconds()
            self.wait(min(60.0, max(0.001, delay)))
        return result


def _profile():
    from astropilot.user_profile import load_user_profile
    return load_user_profile()


def _weather(latitude, longitude):
    from astro_score import fetch_weather
    return fetch_weather(latitude, longitude)


def _tonight():
    from astro_score import build_tonight_application_service
    return build_tonight_application_service()


def _emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Host Opportunity Alerts cycles with optional notification delivery.')
    parser.add_argument('--config', type=Path, required=True, help='Explicit versioned JSON configuration')
    parser.add_argument('--data-dir', type=Path, required=True, help='Existing user profile and alert ledger directory')
    parser.add_argument('--state-dir', type=Path, help='Dedicated scheduler watermark directory')
    parser.add_argument('--once', action='store_true', help='Poll one current slot and exit')
    args = parser.parse_args(argv)
    previous_data_dir = os.environ.get('ASTROPILOT_DATA_DIR')
    try:
        config = load_config(args.config)
        data_dir = args.data_dir.expanduser().resolve()
        state_dir = args.state_dir or data_dir / 'opportunity_alert_scheduler'
        with host_lock(data_dir / '.opportunity_alert_host.lock'):
            os.environ['ASTROPILOT_DATA_DIR'] = str(data_dir)
            stop = Event()
            with shutdown_signals(stop):
                clock = lambda: datetime.now(timezone.utc)
                runner = OpportunityAlertRunner(tonight_service=PreparingTonightService(
                    profile_provider=_profile, weather_provider=_weather, tonight_factory=_tonight,
                    availability=config.availability), ledger=FileOpportunityAlertLedger(data_dir))
                scheduler = OpportunityAlertScheduler(runner=runner, directory=state_dir,
                    clock=clock, cadence=config.cadence)
                _emit({'event': 'startup', 'interval_seconds': config.cadence.interval // timedelta(seconds=1),
                    'enabled': config.policy.enabled})
                result = OpportunityAlertHost(scheduler=scheduler, policy=config.policy,
                    clock=clock, stop_event=stop, report=_emit,
                    notifier={'disabled': DisabledNotifier, 'macos': MacOSNotifier,
                        'windows': WindowsNotifier}[config.notification_channel]()).run(once=args.once)
                _emit({'event': 'shutdown'})
                if args.once and result is not None and (result.status is SchedulerStatus.ERROR
                        or (result.cycle is not None and result.cycle.status is OpportunityAlertCycleStatus.ERROR)):
                    return 1
        return 0
    except HostAlreadyRunning:
        _emit({'event': 'error', 'reason': 'opportunity_alert_host_already_running'})
        return 1
    except Exception:
        _emit({'event': 'error', 'reason': 'opportunity_alert_host_failed'})
        return 1
    finally:
        if previous_data_dir is None:
            os.environ.pop('ASTROPILOT_DATA_DIR', None)
        else:
            os.environ['ASTROPILOT_DATA_DIR'] = previous_data_dir


if __name__ == '__main__':
    sys.exit(main())
