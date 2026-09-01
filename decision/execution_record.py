from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite


_IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def validate_execution_identity(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _IDENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid_{field}")
    return value


def _utc_datetime(value: object, *, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"invalid_{field}")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    decision_id: str | None
    started_at_utc: datetime
    ended_at_utc: datetime
    object: str
    hours: float
    filter_type: str | None = None

    def __post_init__(self) -> None:
        validate_execution_identity(self.execution_id, field="execution_id")
        if self.decision_id is not None:
            validate_execution_identity(self.decision_id, field="decision_id")

        started_at = _utc_datetime(
            self.started_at_utc,
            field="started_at_utc",
        )
        ended_at = _utc_datetime(
            self.ended_at_utc,
            field="ended_at_utc",
        )
        if ended_at <= started_at:
            raise ValueError("invalid_execution_time_range")

        if not isinstance(self.object, str) or not self.object.strip():
            raise ValueError("invalid_object")
        if (
            isinstance(self.hours, bool)
            or not isinstance(self.hours, (int, float))
            or not isfinite(float(self.hours))
            or self.hours <= 0
        ):
            raise ValueError("invalid_hours")
        if self.filter_type is not None and (
            not isinstance(self.filter_type, str)
            or not self.filter_type.strip()
        ):
            raise ValueError("invalid_filter_type")

        object.__setattr__(self, "started_at_utc", started_at)
        object.__setattr__(self, "ended_at_utc", ended_at)
        object.__setattr__(self, "hours", float(self.hours))
