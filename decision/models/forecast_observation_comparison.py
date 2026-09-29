from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from decision.field_observation import (
    CaptureMethod,
    CloudState,
    Confidence,
    ObservationSourceType,
    QualityFlag,
)
from decision.weather.provider_reliability import WeatherVariable


ALGORITHM_VERSION = "forecast_observation.v1"
FORECAST_SCOPE = "decision_attached_evidence"
_V1_TEMPORAL_POLICY_VERSION = "nearest_forecast_utc.v1"
_V1_MAXIMUM_ABSOLUTE_OFFSET = timedelta(minutes=30)


def _is_canonical_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_float(value: object, *, field_name: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"invalid_{field_name}")
    return value


def _utc(value: datetime, *, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"invalid_{field_name}")
    return value.astimezone(timezone.utc)


class ForecastObservationComparisonStatus(str, Enum):
    COMPARABLE = "comparable"
    PARTIAL = "partial"
    NOT_COMPARABLE = "not_comparable"


class VariableComparisonStatus(str, Enum):
    COMPARABLE = "comparable"
    NOT_COMPARABLE = "not_comparable"


class CloudComparisonOutcome(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class ComparisonReason:
    code: str
    variable: WeatherVariable | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("invalid_comparison_reason_code")
        if self.variable is not None and not isinstance(
            self.variable, WeatherVariable
        ):
            raise ValueError("invalid_comparison_reason_variable")
        object.__setattr__(self, "code", self.code.strip())


@dataclass(frozen=True, slots=True)
class TemporalComparisonPolicy:
    version: str = "nearest_forecast_utc.v1"
    maximum_absolute_offset: timedelta = timedelta(minutes=30)
    timezone_name: str = "UTC"
    selection_mode: str = "nearest_per_variable"
    interpolation_enabled: bool = False
    averaging_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("invalid_temporal_policy_version")
        if (
            not isinstance(self.maximum_absolute_offset, timedelta)
            or self.maximum_absolute_offset < timedelta(0)
        ):
            raise ValueError("invalid_maximum_absolute_offset")
        if (
            self.version.strip() == _V1_TEMPORAL_POLICY_VERSION
            and self.maximum_absolute_offset > _V1_MAXIMUM_ABSOLUTE_OFFSET
        ):
            raise ValueError("v1_maximum_absolute_offset_exceeded")
        if self.timezone_name != "UTC":
            raise ValueError("temporal_policy_must_use_utc")
        if self.selection_mode != "nearest_per_variable":
            raise ValueError("unsupported_temporal_selection_mode")
        if self.interpolation_enabled or self.averaging_enabled:
            raise ValueError("forecast_interpolation_or_averaging_not_supported")
        object.__setattr__(self, "version", self.version.strip())


@dataclass(frozen=True, slots=True)
class CloudMappingComparisonPolicy:
    version: str = "cloud_mapping.v1"
    boundaries_percent: tuple[float, float, float, float] = (
        10.0,
        25.0,
        50.0,
        80.0,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("invalid_cloud_mapping_policy_version")
        if (
            type(self.boundaries_percent) is not tuple
            or any(
                type(value) is not float or not math.isfinite(value)
                for value in self.boundaries_percent
            )
        ):
            raise ValueError("invalid_cloud_mapping_boundaries")
        if self.boundaries_percent != (10.0, 25.0, 50.0, 80.0):
            raise ValueError("unsupported_cloud_mapping_boundaries")
        object.__setattr__(self, "version", self.version.strip())


@dataclass(frozen=True, slots=True)
class ForecastObservationParameters:
    temporal_policy: TemporalComparisonPolicy = field(
        default_factory=TemporalComparisonPolicy
    )
    cloud_mapping_policy: CloudMappingComparisonPolicy = field(
        default_factory=CloudMappingComparisonPolicy
    )

    def __post_init__(self) -> None:
        if not isinstance(self.temporal_policy, TemporalComparisonPolicy):
            raise ValueError("invalid_temporal_policy")
        if not isinstance(
            self.cloud_mapping_policy, CloudMappingComparisonPolicy
        ):
            raise ValueError("invalid_cloud_mapping_policy")


@dataclass(frozen=True, slots=True)
class ObservationComparisonProvenance:
    source_type: ObservationSourceType
    source_id: str | None
    capture_method: CaptureMethod
    confidence: Confidence
    quality_flags: tuple[QualityFlag, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, ObservationSourceType):
            raise ValueError("invalid_observation_source_type")
        if self.source_id is not None and (
            not isinstance(self.source_id, str) or not self.source_id.strip()
        ):
            raise ValueError("invalid_observation_source_id")
        if not isinstance(self.capture_method, CaptureMethod):
            raise ValueError("invalid_observation_capture_method")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("invalid_observation_confidence")
        flags = tuple(self.quality_flags)
        if any(not isinstance(flag, QualityFlag) for flag in flags):
            raise ValueError("invalid_observation_quality_flags")
        if len(set(flags)) != len(flags):
            raise ValueError("duplicate_observation_quality_flags")
        object.__setattr__(self, "quality_flags", flags)


@dataclass(frozen=True, slots=True)
class ForecastPointProvenance:
    provider_id: str
    model_id: str | None
    retrieved_at_utc: datetime
    forecast_for_utc: datetime
    temporal_offset: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("invalid_forecast_provider_id")
        if self.model_id is not None and (
            not isinstance(self.model_id, str) or not self.model_id.strip()
        ):
            raise ValueError("invalid_forecast_model_id")
        object.__setattr__(
            self,
            "retrieved_at_utc",
            _utc(self.retrieved_at_utc, field_name="forecast_retrieved_at_utc"),
        )
        object.__setattr__(
            self,
            "forecast_for_utc",
            _utc(self.forecast_for_utc, field_name="forecast_for_utc"),
        )
        if not isinstance(self.temporal_offset, timedelta):
            raise ValueError("invalid_forecast_temporal_offset")


@dataclass(frozen=True, slots=True)
class NumericVariableComparison:
    variable: WeatherVariable
    status: VariableComparisonStatus
    unit: str
    forecast_value: float | None = None
    observed_value: float | None = None
    signed_error: float | None = None
    absolute_error: float | None = None
    forecast_point: ForecastPointProvenance | None = None
    reasons: tuple[ComparisonReason, ...] = ()

    def __post_init__(self) -> None:
        if self.variable not in (
            WeatherVariable.TEMPERATURE_C,
            WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
            WeatherVariable.WIND_SPEED_KMH,
        ):
            raise ValueError("unsupported_numeric_comparison_variable")
        if not isinstance(self.status, VariableComparisonStatus):
            raise ValueError("invalid_variable_comparison_status")
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError("invalid_numeric_comparison_unit")
        reasons = tuple(self.reasons)
        if any(not isinstance(reason, ComparisonReason) for reason in reasons):
            raise ValueError("invalid_numeric_comparison_reasons")
        object.__setattr__(self, "reasons", reasons)
        for field_name in (
            "forecast_value",
            "observed_value",
            "signed_error",
            "absolute_error",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _finite_float(value, field_name=field_name)
        values = (
            self.forecast_value,
            self.observed_value,
            self.signed_error,
            self.absolute_error,
            self.forecast_point,
        )
        if self.status is VariableComparisonStatus.COMPARABLE:
            if any(value is None for value in values) or reasons:
                raise ValueError("incomplete_comparable_numeric_result")
            if self.absolute_error != abs(self.signed_error):
                raise ValueError("invalid_numeric_absolute_error")
            if self.signed_error != self.forecast_value - self.observed_value:
                raise ValueError("invalid_numeric_signed_error")
        elif any(value is not None for value in values) or not reasons:
            raise ValueError("invalid_not_comparable_numeric_result")


@dataclass(frozen=True, slots=True)
class CloudVariableComparison:
    variable: WeatherVariable
    status: VariableComparisonStatus
    unit: str
    forecast_coverage_percent: float | None = None
    predicted_condition: CloudState | None = None
    observed_condition: CloudState | None = None
    outcome: CloudComparisonOutcome | None = None
    confusion_cell: tuple[CloudState, CloudState] | None = None
    forecast_point: ForecastPointProvenance | None = None
    reasons: tuple[ComparisonReason, ...] = ()

    def __post_init__(self) -> None:
        if self.variable is not WeatherVariable.CLOUD_COVER_PERCENT:
            raise ValueError("invalid_cloud_comparison_variable")
        if not isinstance(self.status, VariableComparisonStatus):
            raise ValueError("invalid_variable_comparison_status")
        if self.unit != "%":
            raise ValueError("invalid_cloud_comparison_unit")
        reasons = tuple(self.reasons)
        if any(not isinstance(reason, ComparisonReason) for reason in reasons):
            raise ValueError("invalid_cloud_comparison_reasons")
        object.__setattr__(self, "reasons", reasons)
        if self.forecast_coverage_percent is not None:
            _finite_float(
                self.forecast_coverage_percent,
                field_name="forecast_coverage_percent",
            )
        values = (
            self.forecast_coverage_percent,
            self.predicted_condition,
            self.observed_condition,
            self.outcome,
            self.confusion_cell,
            self.forecast_point,
        )
        if self.status is VariableComparisonStatus.COMPARABLE:
            if any(value is None for value in values) or reasons:
                raise ValueError("incomplete_comparable_cloud_result")
            if self.observed_condition is CloudState.UNKNOWN:
                raise ValueError("unknown_cloud_cannot_be_comparable")
            expected_cell = (self.predicted_condition, self.observed_condition)
            if self.confusion_cell != expected_cell:
                raise ValueError("invalid_cloud_confusion_cell")
            expected_outcome = (
                CloudComparisonOutcome.MATCH
                if self.predicted_condition is self.observed_condition
                else CloudComparisonOutcome.MISMATCH
            )
            if self.outcome is not expected_outcome:
                raise ValueError("invalid_cloud_comparison_outcome")
        elif any(value is not None for value in values) or not reasons:
            raise ValueError("invalid_not_comparable_cloud_result")


VariableComparison = NumericVariableComparison | CloudVariableComparison


@dataclass(frozen=True, slots=True)
class ForecastObservationComparison:
    comparison_id: str
    identity_persistable: bool
    computed_at_utc: datetime
    decision_id: str | None
    observation_id: str
    execution_id: str | None
    source_digest: str
    parameters: ForecastObservationParameters
    observation_provenance: ObservationComparisonProvenance
    results: tuple[VariableComparison, ...]
    status: ForecastObservationComparisonStatus
    reasons: tuple[ComparisonReason, ...]
    algorithm_version: str = ALGORITHM_VERSION
    forecast_scope: str = FORECAST_SCOPE

    def __post_init__(self) -> None:
        if not _is_canonical_sha256(self.comparison_id):
            raise ValueError("invalid_comparison_id")
        if type(self.identity_persistable) is not bool:
            raise ValueError("invalid_identity_persistable")
        if not isinstance(self.observation_id, str) or not self.observation_id:
            raise ValueError("invalid_observation_id")
        if not _is_canonical_sha256(self.source_digest):
            raise ValueError("invalid_source_digest")
        if not isinstance(self.parameters, ForecastObservationParameters):
            raise ValueError("invalid_forecast_observation_parameters")
        if not isinstance(
            self.observation_provenance, ObservationComparisonProvenance
        ):
            raise ValueError("invalid_observation_comparison_provenance")
        if not isinstance(self.status, ForecastObservationComparisonStatus):
            raise ValueError("invalid_forecast_observation_comparison_status")
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version:
            raise ValueError("invalid_algorithm_version")
        if self.forecast_scope != FORECAST_SCOPE:
            raise ValueError("invalid_forecast_scope")
        results = tuple(self.results)
        if any(
            not isinstance(
                result,
                (NumericVariableComparison, CloudVariableComparison),
            )
            for result in results
        ):
            raise ValueError("invalid_variable_comparison_result")
        variables = tuple(result.variable for result in results)
        if len(set(variables)) != len(variables):
            raise ValueError("duplicate_variable_comparison_result")
        reasons = tuple(self.reasons)
        if any(not isinstance(reason, ComparisonReason) for reason in reasons):
            raise ValueError("invalid_comparison_reasons")
        comparable_count = sum(
            result.status is VariableComparisonStatus.COMPARABLE
            for result in results
        )
        if self.status is ForecastObservationComparisonStatus.COMPARABLE and (
            not results or comparable_count != len(results) or reasons
        ):
            raise ValueError("invalid_comparable_comparison")
        if self.status is ForecastObservationComparisonStatus.PARTIAL and (
            comparable_count == 0 or comparable_count == len(results)
        ):
            raise ValueError("invalid_partial_comparison")
        if (
            self.status is ForecastObservationComparisonStatus.NOT_COMPARABLE
            and comparable_count != 0
        ):
            raise ValueError("invalid_not_comparable_comparison")
        if not results and not reasons:
            raise ValueError("empty_comparison_requires_reason")
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(
            self,
            "computed_at_utc",
            _utc(self.computed_at_utc, field_name="computed_at_utc"),
        )
