from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from decision.execution_record import validate_execution_identity


class CloudCondition(str, Enum):
    CLEAR = "clear"
    FEW = "few"
    PARTLY_CLOUDY = "partly_cloudy"
    MOSTLY_CLOUDY = "mostly_cloudy"
    OVERCAST = "overcast"


class Transparency(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class SeeingCondition(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


def _utc_datetime(value: object, *, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"invalid_{field}")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class FieldObservation:
    observation_id: str
    execution_id: str
    observed_at_utc: datetime
    cloud_condition: CloudCondition | None
    transparency: Transparency | None
    seeing: SeeingCondition | None
    dew_detected: bool | None

    def __post_init__(self) -> None:
        validate_execution_identity(
            self.observation_id,
            field="observation_id",
        )
        validate_execution_identity(self.execution_id, field="execution_id")
        observed_at = _utc_datetime(
            self.observed_at_utc,
            field="observed_at_utc",
        )

        if self.cloud_condition is not None and not isinstance(
            self.cloud_condition,
            CloudCondition,
        ):
            raise ValueError("invalid_cloud_condition")
        if self.transparency is not None and not isinstance(
            self.transparency,
            Transparency,
        ):
            raise ValueError("invalid_transparency")
        if self.seeing is not None and not isinstance(
            self.seeing,
            SeeingCondition,
        ):
            raise ValueError("invalid_seeing")
        if self.dew_detected is not None and not isinstance(
            self.dew_detected,
            bool,
        ):
            raise ValueError("invalid_dew_detected")
        if all(
            value is None
            for value in (
                self.cloud_condition,
                self.transparency,
                self.seeing,
                self.dew_detected,
            )
        ):
            raise ValueError("field_observation_value_required")

        object.__setattr__(self, "observed_at_utc", observed_at)
