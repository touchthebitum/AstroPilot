"""Explicit foreground Guardian orchestration with opt-in evidence acquisition."""
import argparse
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import errno
import json
import os
from pathlib import Path
import re
import signal
import sys
from threading import Event
from typing import Callable

from astropilot.guardian_notification import GuardianNotificationPolicy, deliver_cycle, local_notifier

from astropilot.guardian_scheduler import (
    GuardianScheduler, GuardianSchedulerCadence, GuardianSchedulerStatus,
)
from astropilot.guardian_scheduler_state import GuardianSchedulerStateStore
from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner
from decision.runners.guardian_runner import GuardianRunner


@dataclass(frozen=True, slots=True)
class GuardianHostConfig:
    cadence: GuardianSchedulerCadence
    enabled: bool = False
    provider: str | None = None
    schema_version: int = 1
    weather_site: dict | None = None
    notification: GuardianNotificationPolicy = GuardianNotificationPolicy()


@dataclass(frozen=True, slots=True)
class GuardianHostProviders:
    evidence: Callable
    session: Callable

    def __post_init__(self):
        if not callable(self.evidence) or not callable(self.session):
            raise ValueError('invalid_providers')


def _unique(pairs):
    doc = {}
    for key, value in pairs:
        if key in doc:
            raise ValueError('duplicate_key')
        doc[key] = value
    return doc


def _constant(value):
    raise ValueError('nonfinite_number')


def load_config(path):
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'),
                         object_pairs_hook=_unique, parse_constant=_constant)
        if (not isinstance(doc, dict)
                or not {'schema_version', 'interval_seconds', 'anchor'} <= set(doc)
                or not set(doc) <= {'schema_version', 'interval_seconds', 'anchor', 'enabled', 'provider', 'weather_site', 'notification'}
                or type(doc['schema_version']) is not int or doc['schema_version'] != 1
                or type(doc['interval_seconds']) is not int or doc['interval_seconds'] <= 0
                or type(doc.get('enabled', False)) is not bool
                or not isinstance(doc['anchor'], str)):
            raise ValueError('invalid_config')
        provider = doc.get('provider')
        if provider is not None and (not isinstance(provider, str)
                or re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', provider) is None):
            raise ValueError('invalid_provider_identifier')
        if doc.get('enabled', False) and provider is None:
            raise ValueError('provider_required')
        site = doc.get('weather_site')
        if site is not None:
            from astropilot.guardian_live_evidence import ProductionGuardianWeatherAdapter
            if not isinstance(site, dict) or set(site) != {'latitude', 'longitude', 'timeout_seconds'}:
                raise ValueError('weather_site_invalid')
            ProductionGuardianWeatherAdapter(**site)
        cadence = GuardianSchedulerCadence(interval=timedelta(seconds=doc['interval_seconds']),
                                          anchor=datetime.fromisoformat(doc['anchor']))
        return GuardianHostConfig(cadence, doc.get('enabled', False), provider, weather_site=site,
            notification=GuardianNotificationPolicy.from_config(doc.get('notification', {})))
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError('config_invalid') from error


class HostAlreadyRunning(RuntimeError):
    """The Guardian lifetime lock already has an owner."""


@contextmanager
def host_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise HostAlreadyRunning('host_already_running') from error
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


@contextmanager
def _quiet_dependencies():
    # Serial foreground host owns diagnostics; never expose provider prose/errors.
    with open(os.devnull, 'w', encoding='utf-8') as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield


def cycle_diagnostic(result):
    cycle = result.cycle
    assessment = cycle.assessment if cycle else None
    return {'event': 'cycle', 'slot': result.slot.isoformat() if result.slot else None,
            'status': result.status.value, 'reason': result.reason,
            'cycle_status': cycle.status.value if cycle else None,
            'risk': assessment.risk_level.name if assessment else None,
            'action': cycle.recommended_action.name if cycle else None,
            'decision_eligible': cycle.decision_eligible if cycle else False,
            'session_state': assessment.session_state.name if assessment else None,
            'session_applicability': assessment.action_applicability.name if assessment else None,
            'errors': list(cycle.errors) if cycle else []}


class GuardianHost:
    def __init__(self, *, scheduler, cadence, clock, stop_event, report, wait=None, notifier=None):
        self.notifier = notifier
        self.scheduler = scheduler
        self.cadence = cadence
        self.clock = clock
        self.stop_event = stop_event
        self.report = report
        self.wait = stop_event.wait if wait is None else wait

    def run(self, *, once=False):
        while not self.stop_event.is_set():
            with _quiet_dependencies():
                result = self.scheduler.poll()
            self.report(cycle_diagnostic(result))
            if result.status is GuardianSchedulerStatus.ERROR:
                self.report({'event': 'error', 'reason': result.reason})
                return 5 if result.reason == 'state_error' else 6
            if result.status is GuardianSchedulerStatus.COMPLETED and self.notifier is not None:
                with _quiet_dependencies():
                    delivery = deliver_cycle(result.cycle, self.notifier)
                self.report({'event': 'notification', 'status': delivery.status.value, 'reason': delivery.reason})
            if once:
                return 0
            next_due = (self.cadence.anchor if result.slot is None
                        else result.slot + self.cadence.interval)
            while not self.stop_event.is_set():
                remaining = (next_due - self.clock()).total_seconds()
                if remaining <= 0:
                    break
                self.wait(min(60.0, remaining))
        return 0


def _emit(event):
    print(json.dumps(event, sort_keys=True, allow_nan=False), flush=True)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('cli_invalid')


def main(argv=None, *, provider_factories=None, clock=None):
    parser = _Parser(description='Foreground Guardian host with explicit injected providers.')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--once', action='store_true')
    started = False
    phase = 'config'
    try:
        args = parser.parse_args(argv)
        config = load_config(args.config)
        _emit({'event': 'startup', 'config_version': config.schema_version,
               'enabled': config.enabled,
               'interval_seconds': config.cadence.interval // timedelta(seconds=1),
               'anchor': config.cadence.anchor.isoformat()})
        started = True
        if not config.enabled:
            return 0
        phase = 'lock'
        data_dir = args.data_dir.expanduser().resolve()
        with host_lock(data_dir / '.guardian_host.lock'):
            stop = Event()
            phase = 'host'
            with shutdown_signals(stop):
                if stop.is_set():
                    return 0
                phase = 'provider'
                if provider_factories is None:
                    from astropilot.guardian_live_evidence import PROVIDER_ID, ProductionGuardianWeatherAdapter
                    def weather_factory():
                        if config.weather_site is None:
                            raise ValueError('weather_site_required')
                        return GuardianHostProviders(
                            ProductionGuardianWeatherAdapter(**config.weather_site), lambda _: None)
                    registry = {PROVIDER_ID: weather_factory}
                else:
                    registry = provider_factories
                factory = registry.get(config.provider)
                if factory is None:
                    _emit({'event': 'error', 'reason': 'provider_unavailable'})
                    return 3
                with _quiet_dependencies():
                    providers = factory()
                if not isinstance(providers, GuardianHostProviders):
                    raise ValueError('invalid_provider_factory')
                phase = 'host'
                host_clock = clock or (lambda: datetime.now(timezone.utc))
                runner = GuardianPeriodicRunner(evidence_provider=providers.evidence,
                    session_context_provider=providers.session, guardian_runner=GuardianRunner())
                scheduler = GuardianScheduler(runner=runner, clock=host_clock,
                    cadence=config.cadence,
                    state_store=GuardianSchedulerStateStore(args.state_dir or data_dir))
                return GuardianHost(scheduler=scheduler, cadence=config.cadence,
                    clock=host_clock, stop_event=stop, report=_emit,
                    notifier=local_notifier(config.notification) if config.notification.enabled else None).run(once=args.once)
    except HostAlreadyRunning:
        _emit({'event': 'error', 'reason': 'host_already_running'})
        return 4
    except Exception:
        reason, code = {'config': ('config_invalid', 2), 'lock': ('host_lock_failed', 4),
                        'provider': ('provider_factory_error', 3),
                        'host': ('host_failed', 1)}[phase]
        _emit({'event': 'error', 'reason': reason})
        return code
    finally:
        if started:
            _emit({'event': 'shutdown'})


if __name__ == '__main__':
    sys.exit(main())
