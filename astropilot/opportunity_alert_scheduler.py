"""Current-slot orchestration; business decisions belong exclusively to the runner."""
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from threading import Lock

from astropilot.file_lock import exclusive_file_lock
from decision.runners.opportunity_alert_runner import OpportunityAlertCycleResult, OpportunityAlertCycleStatus


def utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('scheduler_aware_time_required')
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class SchedulerCadence:
    interval: timedelta = timedelta(hours=1)
    anchor: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def __post_init__(self):
        if (not isinstance(self.interval, timedelta) or self.interval <= timedelta(0)
                or self.interval.microseconds):
            raise ValueError('scheduler_integral_positive_seconds_required')
        object.__setattr__(self, 'anchor', utc(self.anchor))

    def slot(self, now):
        now = utc(now)
        return None if now < self.anchor else self.anchor + ((now - self.anchor) // self.interval) * self.interval


class SchedulerStatus(str, Enum):
    COMPLETED = 'COMPLETED'
    SKIPPED = 'SKIPPED'
    OVERLAP = 'OVERLAP'
    ERROR = 'ERROR'


@dataclass(frozen=True, slots=True)
class SchedulerResult:
    status: SchedulerStatus
    slot: datetime | None
    reason: str
    cycle: OpportunityAlertCycleResult | None = None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


class SchedulerStateStore:
    """One directory per stable user/context/cadence; callers hold lock throughout."""
    def __init__(self, directory, cadence):
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / 'opportunity_alert_scheduler.json'
        self.lock_path = self.directory / '.opportunity_alert_scheduler.lock'
        self.cadence = cadence

    def load(self):
        config = {'interval_seconds': self.cadence.interval // timedelta(seconds=1),
            'anchor': self.cadence.anchor.isoformat()}
        try:
            text = self.path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return {'schema_version': 1, 'cadence': config, 'last_started_slot': None,
                'last_completed_slot': None, 'last_result': None}
        doc = json.loads(text, object_pairs_hook=_unique)
        if (not isinstance(doc, dict) or set(doc) != {'schema_version', 'cadence',
                'last_started_slot', 'last_completed_slot', 'last_result'}
                or type(doc['schema_version']) is not int or doc['schema_version'] != 1
                or doc['cadence'] != config):
            raise ValueError('invalid_scheduler_state')
        times = []
        for key in ('last_started_slot', 'last_completed_slot'):
            value = doc[key]
            at = utc(datetime.fromisoformat(value)) if isinstance(value, str) else None
            if value is not None and at is None:
                raise ValueError('invalid_slot')
            if at is not None and self.cadence.slot(at) != at:
                raise ValueError('unaligned_slot')
            times.append(at)
        started, completed = times
        result = doc['last_result']
        if completed is not None and (started is None or completed > started):
            raise ValueError('invalid_watermark')
        if completed is None:
            if result is not None:
                raise ValueError('unexpected_result')
        elif (not isinstance(result, dict) or set(result) != {'status', 'reason_codes'}
                or result['status'] not in {s.value for s in OpportunityAlertCycleStatus}
                or not isinstance(result['reason_codes'], list)
                or any(not isinstance(r, str) for r in result['reason_codes'])):
            raise ValueError('invalid_result')
        return doc

    def write(self, doc):
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                    prefix='.opportunity_alert_scheduler.', suffix='.tmp', delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(doc, temporary, sort_keys=True, allow_nan=False)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            if os.name != 'nt':
                descriptor = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


class OpportunityAlertScheduler:
    def __init__(self, *, runner, directory, clock, cadence=SchedulerCadence()):
        self.runner = runner
        self.clock = clock
        self.cadence = cadence
        self.store = SchedulerStateStore(directory, cadence)
        self._guard = Lock()

    def poll(self, *, policy, now=None, cycle_time=None, **tonight_inputs):
        slot = self.cadence.slot(self.clock() if now is None else now)
        if slot is None:
            return SchedulerResult(SchedulerStatus.SKIPPED, None, 'before_anchor')
        at = slot if cycle_time is None else utc(cycle_time)
        if self.cadence.slot(at) != slot:
            raise ValueError('scheduler_cycle_time_outside_slot')
        if not self._guard.acquire(blocking=False):
            return SchedulerResult(SchedulerStatus.OVERLAP, slot, 'cycle_in_progress')
        cycle = None
        try:
            with exclusive_file_lock(self.store.lock_path):
                doc = self.store.load()
                last = doc['last_started_slot']
                if last is not None and slot <= utc(datetime.fromisoformat(last)):
                    return SchedulerResult(SchedulerStatus.SKIPPED, slot, 'slot_already_reserved')
                doc['last_started_slot'] = slot.isoformat()
                self.store.write(doc)
                try:
                    cycle = self.runner.run_cycle(policy=policy, logical_time=at, **tonight_inputs)
                    if not isinstance(cycle, OpportunityAlertCycleResult):
                        raise TypeError('invalid_cycle_result')
                except Exception:
                    cycle = OpportunityAlertCycleResult(OpportunityAlertCycleStatus.ERROR,
                        False, at, ('scheduler_runner_failed',))
                doc['last_completed_slot'] = slot.isoformat()
                doc['last_result'] = {'status': cycle.status.value, 'reason_codes': list(cycle.reason_codes)}
                self.store.write(doc)
                return SchedulerResult(SchedulerStatus.COMPLETED, slot, 'cycle_completed', cycle)
        except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
            return SchedulerResult(SchedulerStatus.ERROR, slot, 'scheduler_state_unavailable', cycle)
        finally:
            self._guard.release()
