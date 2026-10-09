"""Caller-driven, in-memory Guardian scheduling; no evaluation or execution authority."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Callable

from decision.models.guardian_cycle import GuardianCycleResult, GuardianCycleStatus
from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner

VERSION = 'guardian-scheduler-v1'


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('guardian_scheduler_aware_time_required')
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class GuardianSchedulerCadence:
    interval: timedelta
    anchor: datetime
    version: str = VERSION

    def __post_init__(self):
        if (not isinstance(self.interval, timedelta) or self.interval <= timedelta(0)
                or self.interval.microseconds):
            raise ValueError('guardian_scheduler_integral_positive_seconds_required')
        if self.version != VERSION:
            raise ValueError('guardian_scheduler_unsupported_version')
        object.__setattr__(self, 'anchor', _utc(self.anchor))

    def slot(self, current_time: datetime) -> datetime | None:
        current_time = _utc(current_time)
        if current_time < self.anchor:
            return None
        return self.anchor + ((current_time - self.anchor) // self.interval) * self.interval


class GuardianSchedulerStatus(str, Enum):
    COMPLETED = 'COMPLETED'
    SKIPPED = 'SKIPPED'
    ERROR = 'ERROR'


@dataclass(frozen=True, slots=True)
class GuardianSchedulerResult:
    status: GuardianSchedulerStatus
    slot: datetime | None
    reason: str
    cycle: GuardianCycleResult | None = None
    version: str = VERSION

    def __post_init__(self):
        reasons = {
            GuardianSchedulerStatus.COMPLETED: {'cycle_completed'},
            GuardianSchedulerStatus.SKIPPED: {'before_anchor', 'slot_already_reserved', 'cycle_in_progress'},
            GuardianSchedulerStatus.ERROR: {'cycle_error'},
        }
        if not isinstance(self.status, GuardianSchedulerStatus) or self.reason not in reasons[self.status]:
            raise ValueError('guardian_scheduler_invalid_result')
        if self.version != VERSION:
            raise ValueError('guardian_scheduler_unsupported_version')


class GuardianScheduler:
    """One instance per context; reservations do not survive instance recreation."""
    def __init__(self, *, runner: GuardianPeriodicRunner, clock: Callable[[], datetime],
                 cadence: GuardianSchedulerCadence):
        self._runner = runner
        self._clock = clock
        self._cadence = cadence
        self._guard = Lock()
        self._last_reserved_slot: datetime | None = None

    def poll(self) -> GuardianSchedulerResult:
        slot = self._cadence.slot(self._clock())
        if slot is None:
            return GuardianSchedulerResult(GuardianSchedulerStatus.SKIPPED, None, 'before_anchor')
        if not self._guard.acquire(blocking=False):
            return GuardianSchedulerResult(GuardianSchedulerStatus.SKIPPED, slot, 'cycle_in_progress')
        try:
            if self._last_reserved_slot is not None and slot <= self._last_reserved_slot:
                return GuardianSchedulerResult(GuardianSchedulerStatus.SKIPPED, slot, 'slot_already_reserved')
            self._last_reserved_slot = slot
            try:
                cycle = self._runner.run_cycle(logical_time=slot)
                if (not isinstance(cycle, GuardianCycleResult) or cycle.logical_time != slot
                        or not isinstance(cycle.status, GuardianCycleStatus)):
                    raise TypeError('invalid_cycle_result')
            except Exception:
                return GuardianSchedulerResult(GuardianSchedulerStatus.ERROR, slot, 'cycle_error')
            if cycle.status is GuardianCycleStatus.ERROR:
                return GuardianSchedulerResult(GuardianSchedulerStatus.ERROR, slot, 'cycle_error', cycle)
            return GuardianSchedulerResult(GuardianSchedulerStatus.COMPLETED, slot, 'cycle_completed', cycle)
        finally:
            self._guard.release()
