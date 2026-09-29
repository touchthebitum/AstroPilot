from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


_IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
LEGACY_LINEAGE_INCOMPLETE = "legacy_lineage_incomplete"


class CloudState(str, Enum):
    CLEAR = "clear"
    FEW = "few"
    PARTLY_CLOUDY = "partly_cloudy"
    MOSTLY_CLOUDY = "mostly_cloudy"
    OVERCAST = "overcast"
    UNKNOWN = "unknown"


CloudCondition = CloudState


class Transparency(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class SeeingCondition(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class SurfaceCondition(str, Enum):
    DRY = "dry"
    DAMP = "damp"
    DEW_PRESENT = "dew_present"
    FROST_PRESENT = "frost_present"
    UNKNOWN = "unknown"


class StopReason(str, Enum):
    COMPLETED = "completed"
    CLOUDS = "clouds"
    DEW = "dew"
    WIND = "wind"
    TECHNICAL = "technical"
    TARGET_LOST = "target_lost"
    USER = "user"
    DAYLIGHT = "daylight"
    NOT_STARTED = "not_started"
    OTHER = "other"
    UNKNOWN = "unknown"


class ObservationSourceType(str, Enum):
    USER = "user"
    WEATHER_STATION = "weather_station"
    ASIAIR = "asiair"
    FILE_IMPORT = "file_import"
    OTHER_DEVICE = "other_device"


class CaptureMethod(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    IMPORTED = "imported"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class QualityFlag(str, Enum):
    ESTIMATED = "estimated"
    SENSOR_UNCALIBRATED = "sensor_uncalibrated"
    TIME_UNCERTAIN = "time_uncertain"
    LOCATION_UNCERTAIN = "location_uncertain"
    PARTIAL = "partial"
    IMPORTED = "imported"
    OUTLIER_SUSPECTED = "outlier_suspected"
    LEGACY_LINEAGE_INCOMPLETE = LEGACY_LINEAGE_INCOMPLETE


def validate_observation_identity(value: object, *, field: str) -> str:
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


def _optional_finite(
    value: object,
    *,
    field: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid_{field}")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"invalid_{field}")
    if minimum is not None and normalized < minimum:
        raise ValueError(f"invalid_{field}")
    if maximum is not None and normalized > maximum:
        raise ValueError(f"invalid_{field}")
    return normalized


def _optional_count(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid_{field}")
    return value


def _optional_enum(value: object, kind: type[Enum], *, field: str) -> None:
    if value is not None and type(value) is not kind:
        raise ValueError(f"invalid_{field}")


@dataclass(frozen=True, slots=True)
class ObservedConditions:
    temperature_c: float | None = None
    relative_humidity_percent: float | None = None
    cloud_state: CloudState | None = None
    transparency: Transparency | None = None
    seeing: SeeingCondition | None = None
    wind_speed_kmh: float | None = None
    surface_condition: SurfaceCondition | None = None
    moon_halo: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "temperature_c",
            _optional_finite(self.temperature_c, field="temperature_c"),
        )
        object.__setattr__(
            self,
            "relative_humidity_percent",
            _optional_finite(
                self.relative_humidity_percent,
                field="relative_humidity_percent",
                minimum=0,
                maximum=100,
            ),
        )
        object.__setattr__(
            self,
            "wind_speed_kmh",
            _optional_finite(
                self.wind_speed_kmh,
                field="wind_speed_kmh",
                minimum=0,
            ),
        )
        _optional_enum(self.cloud_state, CloudState, field="cloud_state")
        _optional_enum(self.transparency, Transparency, field="transparency")
        _optional_enum(self.seeing, SeeingCondition, field="seeing")
        _optional_enum(
            self.surface_condition,
            SurfaceCondition,
            field="surface_condition",
        )
        if self.moon_halo is not None and type(self.moon_halo) is not bool:
            raise ValueError("invalid_moon_halo")

    def has_fact(self) -> bool:
        return any(
            value is not None
            for value in (
                self.temperature_c,
                self.relative_humidity_percent,
                self.cloud_state,
                self.transparency,
                self.seeing,
                self.wind_speed_kmh,
                self.surface_condition,
                self.moon_halo,
            )
        )


@dataclass(frozen=True, slots=True)
class ObservedAcquisition:
    attempted_frames: int | None = None
    usable_frames: int | None = None
    stop_reason: StopReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attempted_frames",
            _optional_count(self.attempted_frames, field="attempted_frames"),
        )
        object.__setattr__(
            self,
            "usable_frames",
            _optional_count(self.usable_frames, field="usable_frames"),
        )
        _optional_enum(self.stop_reason, StopReason, field="stop_reason")
        if self.usable_frames is not None and self.attempted_frames is None:
            raise ValueError("usable_frames_requires_attempted_frames")
        if (
            self.usable_frames is not None
            and self.usable_frames > self.attempted_frames
        ):
            raise ValueError("usable_frames_exceed_attempted_frames")

    def has_fact(self) -> bool:
        return any(
            value is not None
            for value in (
                self.attempted_frames,
                self.usable_frames,
                self.stop_reason,
            )
        )


@dataclass(frozen=True, slots=True)
class ObservedTechnical:
    hfr: float | None = None
    hfr_unit: str | None = None
    sky_background: float | None = None
    sky_background_unit: str | None = None
    guiding_rms_arcsec: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hfr",
            _optional_finite(self.hfr, field="hfr", minimum=0),
        )
        object.__setattr__(
            self,
            "sky_background",
            _optional_finite(
                self.sky_background,
                field="sky_background",
                minimum=0,
            ),
        )
        object.__setattr__(
            self,
            "guiding_rms_arcsec",
            _optional_finite(
                self.guiding_rms_arcsec,
                field="guiding_rms_arcsec",
                minimum=0,
            ),
        )
        self._validate_unit_pair(self.hfr, self.hfr_unit, field="hfr")
        self._validate_unit_pair(
            self.sky_background,
            self.sky_background_unit,
            field="sky_background",
        )

    @staticmethod
    def _validate_unit_pair(value: float | None, unit: object, *, field: str):
        if value is None:
            if unit is not None:
                raise ValueError(f"{field}_unit_without_value")
            return
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError(f"{field}_unit_required")

    def has_fact(self) -> bool:
        return any(
            value is not None
            for value in (self.hfr, self.sky_background, self.guiding_rms_arcsec)
        )


@dataclass(frozen=True, slots=True)
class ObservationProvenance:
    source_type: ObservationSourceType
    capture_method: CaptureMethod
    source_id: str | None = None
    imported_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        if type(self.source_type) is not ObservationSourceType:
            raise ValueError("invalid_source_type")
        if type(self.capture_method) is not CaptureMethod:
            raise ValueError("invalid_capture_method")
        if self.source_id is not None and (
            not isinstance(self.source_id, str) or not self.source_id.strip()
        ):
            raise ValueError("invalid_source_id")
        if self.imported_at_utc is not None:
            object.__setattr__(
                self,
                "imported_at_utc",
                _utc_datetime(self.imported_at_utc, field="imported_at_utc"),
            )
        if (
            self.capture_method is CaptureMethod.IMPORTED
            and self.imported_at_utc is None
        ):
            raise ValueError("imported_at_utc_required")


@dataclass(frozen=True, slots=True)
class ObservationQuality:
    confidence: Confidence = Confidence.UNKNOWN
    flags: tuple[QualityFlag, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if type(self.confidence) is not Confidence:
            raise ValueError("invalid_confidence")
        if type(self.flags) is not tuple or any(
            type(value) is not QualityFlag for value in self.flags
        ):
            raise ValueError("invalid_quality_flags")
        if len(set(self.flags)) != len(self.flags):
            raise ValueError("duplicate_quality_flags")


@dataclass(frozen=True, slots=True)
class FieldObservation:
    observation_id: str
    decision_id: str | None
    execution_id: str | None
    observed_at_utc: datetime
    recorded_at_utc: datetime
    supersedes_observation_id: str | None
    conditions: ObservedConditions
    acquisition: ObservedAcquisition
    technical: ObservedTechnical
    provenance: ObservationProvenance
    quality: ObservationQuality

    def __post_init__(self) -> None:
        validate_observation_identity(self.observation_id, field="observation_id")
        if type(self.quality) is not ObservationQuality:
            raise ValueError("invalid_quality")
        is_legacy = (
            QualityFlag.LEGACY_LINEAGE_INCOMPLETE in self.quality.flags
        )
        if self.decision_id is None:
            if not is_legacy:
                raise ValueError("decision_id_required")
        else:
            validate_observation_identity(self.decision_id, field="decision_id")
            if is_legacy:
                raise ValueError("legacy_lineage_flag_invalid")
        if self.execution_id is not None:
            validate_observation_identity(self.execution_id, field="execution_id")
        if self.supersedes_observation_id is not None:
            validate_observation_identity(
                self.supersedes_observation_id,
                field="supersedes_observation_id",
            )
            if self.supersedes_observation_id == self.observation_id:
                raise ValueError("observation_cannot_supersede_itself")
        observed_at = _utc_datetime(
            self.observed_at_utc,
            field="observed_at_utc",
        )
        recorded_at = _utc_datetime(
            self.recorded_at_utc,
            field="recorded_at_utc",
        )
        if recorded_at < observed_at:
            raise ValueError("recorded_at_precedes_observed_at")
        if type(self.conditions) is not ObservedConditions:
            raise ValueError("invalid_conditions")
        if type(self.acquisition) is not ObservedAcquisition:
            raise ValueError("invalid_acquisition")
        if type(self.technical) is not ObservedTechnical:
            raise ValueError("invalid_technical")
        if type(self.provenance) is not ObservationProvenance:
            raise ValueError("invalid_provenance")
        if not any(
            section.has_fact()
            for section in (self.conditions, self.acquisition, self.technical)
        ):
            raise ValueError("field_observation_value_required")
        object.__setattr__(self, "observed_at_utc", observed_at)
        object.__setattr__(self, "recorded_at_utc", recorded_at)

    @property
    def calibration_eligible(self) -> bool:
        return (
            self.decision_id is not None
            and QualityFlag.LEGACY_LINEAGE_INCOMPLETE not in self.quality.flags
        )

    @property
    def legacy_lineage_incomplete(self) -> bool:
        return not self.calibration_eligible

    @property
    def cloud_condition(self) -> CloudState | None:
        return self.conditions.cloud_state

    @property
    def transparency(self) -> Transparency | None:
        return self.conditions.transparency

    @property
    def seeing(self) -> SeeingCondition | None:
        return self.conditions.seeing

    @property
    def dew_detected(self) -> bool | None:
        surface = self.conditions.surface_condition
        if surface in (SurfaceCondition.DEW_PRESENT, SurfaceCondition.FROST_PRESENT):
            return True
        if surface is SurfaceCondition.DRY:
            return False
        return None
