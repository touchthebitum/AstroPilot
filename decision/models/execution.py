from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class ExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    UNCONFIRMED = "unconfirmed"


def _validate_timestamp(value: datetime):
    if not isinstance(value, datetime):
        raise TypeError("execution_timestamp_must_be_datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("execution_timestamp_timezone_required")


@dataclass(frozen=True, slots=True)
class Execution:
    execution_id: str
    mission_id: str
    status: ExecutionStatus
    actual_start: datetime | None
    actual_end: datetime | None
    actual_duration: timedelta | None

    def __post_init__(self):
        for name in ("execution_id", "mission_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if not isinstance(self.status, ExecutionStatus):
            raise TypeError("Expected ExecutionStatus")

        timing = (self.actual_start, self.actual_end, self.actual_duration)
        if self.status is ExecutionStatus.NOT_STARTED:
            if any(value is not None for value in timing):
                raise ValueError("not_started_requires_no_timing")
            return
        if self.status is ExecutionStatus.UNCONFIRMED:
            if any(value is not None for value in timing):
                raise ValueError("unconfirmed_requires_no_timing")
            return
        if self.status is ExecutionStatus.IN_PROGRESS:
            if (
                self.actual_start is None
                or self.actual_end is not None
                or self.actual_duration is not None
            ):
                raise ValueError("in_progress_requires_start_only")
            _validate_timestamp(self.actual_start)
            return

        if any(value is None for value in timing):
            raise ValueError("closed_execution_requires_timing")
        _validate_timestamp(self.actual_start)
        _validate_timestamp(self.actual_end)
        if not isinstance(self.actual_duration, timedelta):
            raise TypeError("actual_duration_must_be_timedelta")
        if self.actual_duration < timedelta(0):
            raise ValueError("execution_duration_must_be_non_negative")

        elapsed = (
            self.actual_end.astimezone(timezone.utc)
            - self.actual_start.astimezone(timezone.utc)
        )
        if elapsed < timedelta(0):
            raise ValueError("execution_end_precedes_start")
        if self.actual_duration != elapsed:
            raise ValueError("execution_duration_mismatch")
