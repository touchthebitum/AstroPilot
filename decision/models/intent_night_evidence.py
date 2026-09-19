from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite


_DURATION_TOLERANCE_HOURS = 1e-9


@dataclass(frozen=True, slots=True)
class IntentNightEvidence:
    """Observed night evidence for one actionable imaging-field window."""

    imaging_field_id: str
    actionable_window_start: datetime
    actionable_window_end: datetime
    actionable_duration_hours: float
    reference_time: datetime
    moon_illumination: float | None
    moon_altitude_deg: float | None
    moon_separation_deg: float | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.imaging_field_id, str)
            or not self.imaging_field_id.strip()
        ):
            raise ValueError("imaging_field_id must be a non-empty string")

        start_utc = self._to_utc(
            self.actionable_window_start,
            "actionable_window_start",
        )
        end_utc = self._to_utc(
            self.actionable_window_end,
            "actionable_window_end",
        )
        reference_utc = self._to_utc(
            self.reference_time,
            "reference_time",
        )

        if end_utc <= start_utc:
            raise ValueError(
                "actionable_window_end must be after actionable_window_start"
            )

        self._validate_duration(
            self.actionable_duration_hours,
            expected_hours=(end_utc - start_utc).total_seconds() / 3600.0,
        )

        if not start_utc <= reference_utc <= end_utc:
            raise ValueError("reference_time must be within the actionable window")

        self._validate_optional_bounded_value(
            self.moon_illumination,
            "moon_illumination",
            minimum=0.0,
            maximum=1.0,
        )
        self._validate_optional_bounded_value(
            self.moon_altitude_deg,
            "moon_altitude_deg",
            minimum=-90.0,
            maximum=90.0,
        )
        self._validate_optional_bounded_value(
            self.moon_separation_deg,
            "moon_separation_deg",
            minimum=0.0,
            maximum=180.0,
        )

    @staticmethod
    def _to_utc(value: datetime, name: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _validate_duration(value: float, *, expected_hours: float) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
        ):
            raise ValueError("actionable_duration_hours must be a finite number")
        if value <= 0.0:
            raise ValueError("actionable_duration_hours must be positive")
        if abs(float(value) - expected_hours) > _DURATION_TOLERANCE_HOURS:
            raise ValueError(
                "actionable_duration_hours must match the actionable window"
            )

    @staticmethod
    def _validate_optional_bounded_value(
        value: float | None,
        name: str,
        *,
        minimum: float,
        maximum: float,
    ) -> None:
        if value is None:
            return
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
        ):
            raise ValueError(f"{name} must be None or a finite number")
        if not minimum <= value <= maximum:
            raise ValueError(
                f"{name} must satisfy {minimum} <= {name} <= {maximum}"
            )
