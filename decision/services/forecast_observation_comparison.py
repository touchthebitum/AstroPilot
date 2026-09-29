from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum

from decision.field_observation import (
    CloudState,
    FieldObservation,
    QualityFlag,
)
from decision.models.forecast_observation_comparison import (
    ALGORITHM_VERSION,
    FORECAST_SCOPE,
    CloudComparisonOutcome,
    CloudVariableComparison,
    ComparisonReason,
    ForecastObservationComparison,
    ForecastObservationComparisonStatus,
    ForecastObservationParameters,
    ForecastPointProvenance,
    NumericVariableComparison,
    ObservationComparisonProvenance,
    VariableComparison,
    VariableComparisonStatus,
)
from decision.weather.cloud_mapping_policy import map_cloud_cover_to_condition
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.forecast_temporal_candidates import (
    build_forecast_temporal_candidates,
)
from decision.weather.forecast_temporal_selection import (
    ForecastTemporalSelectionError,
    select_forecast_temporal_candidate,
)
from decision.weather.provider_reliability import (
    CANONICAL_UNITS,
    WeatherForecastPoint,
    WeatherValue,
    WeatherVariable,
    calculate_weather_variable_error,
)


class ForecastObservationComparisonInputError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_datetime(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def _canonicalize(value):
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    return value


def _canonical_json(value) -> str:
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_location(location) -> dict:
    return {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "altitude_m": location.altitude_m,
    }


def _canonical_weather_value(value: WeatherValue) -> dict:
    return {
        "variable": value.variable.value,
        "value": value.value,
        "unit": value.unit,
        "aggregation_period_seconds": (
            value.aggregation_period.total_seconds()
            if value.aggregation_period is not None
            else None
        ),
    }


def _canonical_forecast_point(point: WeatherForecastPoint) -> dict:
    return {
        "provider_id": point.provider_id,
        "model_id": point.model_id,
        "retrieved_at_utc": point.retrieved_at_utc,
        "forecast_for_utc": point.forecast_for_utc,
        "requested_location": _canonical_location(point.requested_location),
        "grid_location": _canonical_location(point.grid_location),
        "values": sorted(
            (_canonical_weather_value(value) for value in point.values),
            key=lambda value: value["variable"],
        ),
    }


def _deduplicate_identical_points(
    points: tuple[WeatherForecastPoint, ...],
) -> tuple[WeatherForecastPoint, ...]:
    unique = []
    for point in points:
        if point not in unique:
            unique.append(point)
    return tuple(unique)


def _canonical_evidence(evidence: object) -> dict:
    if evidence is None:
        return {"state": "missing"}
    if not _evidence_is_well_formed(evidence):
        return {"state": "invalid", "type": type(evidence).__name__}
    assert isinstance(evidence, DecisionForecastEvidence)
    points = _deduplicate_identical_points(evidence.forecast_points)
    documents = [_canonical_forecast_point(point) for point in points]
    documents.sort(key=_canonical_json)
    return {"state": "present", "forecast_points": documents}


def _evidence_is_well_formed(evidence: object) -> bool:
    return (
        isinstance(evidence, DecisionForecastEvidence)
        and isinstance(evidence.forecast_points, tuple)
        and all(
            isinstance(point, WeatherForecastPoint)
            for point in evidence.forecast_points
        )
    )


def _canonical_observation(observation: FieldObservation) -> dict:
    return {
        "observation_id": observation.observation_id,
        "decision_id": observation.decision_id,
        "execution_id": observation.execution_id,
        "observed_at_utc": observation.observed_at_utc,
        "recorded_at_utc": observation.recorded_at_utc,
        "supersedes_observation_id": observation.supersedes_observation_id,
        "conditions": asdict(observation.conditions),
        "acquisition": asdict(observation.acquisition),
        "technical": asdict(observation.technical),
        "provenance": asdict(observation.provenance),
        "quality": asdict(observation.quality),
    }


def _parameter_document(parameters: ForecastObservationParameters) -> dict:
    return {
        "temporal_policy": {
            "version": parameters.temporal_policy.version,
            "maximum_absolute_offset_seconds": (
                parameters.temporal_policy.maximum_absolute_offset.total_seconds()
            ),
            "timezone_name": parameters.temporal_policy.timezone_name,
            "selection_mode": parameters.temporal_policy.selection_mode,
            "interpolation_enabled": (
                parameters.temporal_policy.interpolation_enabled
            ),
            "averaging_enabled": parameters.temporal_policy.averaging_enabled,
        },
        "cloud_mapping_policy": {
            "version": parameters.cloud_mapping_policy.version,
            "boundaries_percent": (
                parameters.cloud_mapping_policy.boundaries_percent
            ),
        },
    }


def _source_digest(
    evidence: object,
    observation: FieldObservation,
) -> str:
    return _digest(
        {
            "decision_forecast_evidence": _canonical_evidence(evidence),
            "field_observation": _canonical_observation(observation),
        }
    )


def _comparison_id(
    *,
    observation: FieldObservation,
    source_digest: str,
    algorithm_version: str,
    parameters: ForecastObservationParameters,
) -> str:
    return _digest(
        {
            "decision_id": observation.decision_id,
            "observation_id": observation.observation_id,
            "source_digest": source_digest,
            "algorithm_version": algorithm_version,
            "forecast_scope": FORECAST_SCOPE,
            "parameters": _parameter_document(parameters),
        }
    )


def _observation_provenance(
    observation: FieldObservation,
) -> ObservationComparisonProvenance:
    return ObservationComparisonProvenance(
        source_type=observation.provenance.source_type,
        source_id=observation.provenance.source_id,
        capture_method=observation.provenance.capture_method,
        confidence=observation.quality.confidence,
        quality_flags=observation.quality.flags,
    )


def _point_provenance(
    point: WeatherForecastPoint,
    *,
    observed_at_utc: datetime,
) -> ForecastPointProvenance:
    return ForecastPointProvenance(
        provider_id=point.provider_id,
        model_id=point.model_id,
        retrieved_at_utc=point.retrieved_at_utc,
        forecast_for_utc=point.forecast_for_utc,
        temporal_offset=point.forecast_for_utc - observed_at_utc,
    )


def _observed_values(
    observation: FieldObservation,
) -> tuple[tuple[WeatherVariable, float | CloudState], ...]:
    conditions = observation.conditions
    values = []
    for variable, value in (
        (WeatherVariable.TEMPERATURE_C, conditions.temperature_c),
        (
            WeatherVariable.RELATIVE_HUMIDITY_PERCENT,
            conditions.relative_humidity_percent,
        ),
        (WeatherVariable.WIND_SPEED_KMH, conditions.wind_speed_kmh),
        (WeatherVariable.CLOUD_COVER_PERCENT, conditions.cloud_state),
    ):
        if value is not None:
            values.append((variable, value))
    return tuple(values)


def _not_comparable_result(
    variable: WeatherVariable,
    reason: ComparisonReason,
) -> VariableComparison:
    if variable is WeatherVariable.CLOUD_COVER_PERCENT:
        return CloudVariableComparison(
            variable=variable,
            status=VariableComparisonStatus.NOT_COMPARABLE,
            unit=CANONICAL_UNITS[variable],
            reasons=(reason,),
        )
    return NumericVariableComparison(
        variable=variable,
        status=VariableComparisonStatus.NOT_COMPARABLE,
        unit=CANONICAL_UNITS[variable],
        reasons=(reason,),
    )


def _points_for_variable(
    evidence: DecisionForecastEvidence,
    variable: WeatherVariable,
) -> tuple[WeatherForecastPoint, ...]:
    compatible = tuple(
        point
        for point in evidence.forecast_points
        if any(value.variable is variable for value in point.values)
    )
    return _deduplicate_identical_points(compatible)


def _select_point(
    evidence: DecisionForecastEvidence,
    observation: FieldObservation,
    variable: WeatherVariable,
    parameters: ForecastObservationParameters,
) -> tuple[WeatherForecastPoint | None, ComparisonReason | None]:
    points = _points_for_variable(evidence, variable)
    if not points:
        return None, ComparisonReason(
            code="forecast_variable_unavailable",
            variable=variable,
        )
    candidates = build_forecast_temporal_candidates(
        points,
        observation.observed_at_utc,
    )
    try:
        selected = select_forecast_temporal_candidate(
            candidates,
            maximum_absolute_offset=(
                parameters.temporal_policy.maximum_absolute_offset
            ),
        )
    except ForecastTemporalSelectionError:
        return None, ComparisonReason(
            code="ambiguous_nearest_forecast",
            variable=variable,
        )
    if selected is None:
        return None, ComparisonReason(
            code="forecast_outside_temporal_tolerance",
            variable=variable,
        )
    return selected.forecast_point, None


def _value_for_variable(
    point: WeatherForecastPoint,
    variable: WeatherVariable,
) -> WeatherValue:
    for value in point.values:
        if value.variable is variable:
            return value
    raise AssertionError("selected_forecast_variable_missing")


def _numeric_result(
    *,
    variable: WeatherVariable,
    observed_value: float,
    point: WeatherForecastPoint,
    observation: FieldObservation,
) -> NumericVariableComparison:
    forecast_value = _value_for_variable(point, variable)
    error = calculate_weather_variable_error(
        variable=variable,
        forecast_value=forecast_value.value,
        observed_value=observed_value,
        unit=forecast_value.unit,
    )
    return NumericVariableComparison(
        variable=variable,
        status=VariableComparisonStatus.COMPARABLE,
        unit=error.unit,
        forecast_value=error.forecast_value,
        observed_value=error.observed_value,
        signed_error=error.signed_error,
        absolute_error=error.absolute_error,
        forecast_point=_point_provenance(
            point,
            observed_at_utc=observation.observed_at_utc,
        ),
    )


def _cloud_result(
    *,
    observed_condition: CloudState,
    point: WeatherForecastPoint,
    observation: FieldObservation,
) -> CloudVariableComparison:
    variable = WeatherVariable.CLOUD_COVER_PERCENT
    forecast_value = _value_for_variable(point, variable)
    predicted = map_cloud_cover_to_condition(forecast_value.value)
    outcome = (
        CloudComparisonOutcome.MATCH
        if predicted is observed_condition
        else CloudComparisonOutcome.MISMATCH
    )
    return CloudVariableComparison(
        variable=variable,
        status=VariableComparisonStatus.COMPARABLE,
        unit=forecast_value.unit,
        forecast_coverage_percent=forecast_value.value,
        predicted_condition=predicted,
        observed_condition=observed_condition,
        outcome=outcome,
        confusion_cell=(predicted, observed_condition),
        forecast_point=_point_provenance(
            point,
            observed_at_utc=observation.observed_at_utc,
        ),
    )


def _comparison_status(
    results: tuple[VariableComparison, ...],
) -> ForecastObservationComparisonStatus:
    comparable_count = sum(
        result.status is VariableComparisonStatus.COMPARABLE
        for result in results
    )
    if comparable_count == 0:
        return ForecastObservationComparisonStatus.NOT_COMPARABLE
    if comparable_count == len(results):
        return ForecastObservationComparisonStatus.COMPARABLE
    return ForecastObservationComparisonStatus.PARTIAL


def compare_forecast_to_field_observation(
    evidence: object,
    observation: FieldObservation,
    *,
    computed_at_utc: datetime,
    algorithm_version: str = ALGORITHM_VERSION,
    parameters: ForecastObservationParameters | None = None,
) -> ForecastObservationComparison:
    """Compare immutable decision evidence to one immutable field observation.

    The caller supplies ``computed_at_utc`` so the engine has no clock or other
    side effect. Missing or invalid forecast evidence is represented as a
    structured not-comparable result. A missing/invalid observation raises a
    typed input error because no comparison identity can be constructed.
    """
    if not isinstance(observation, FieldObservation):
        code = (
            "field_observation_missing"
            if observation is None
            else "field_observation_invalid"
        )
        raise ForecastObservationComparisonInputError(code)
    if not isinstance(algorithm_version, str) or not algorithm_version.strip():
        raise ForecastObservationComparisonInputError("invalid_algorithm_version")
    algorithm_version = algorithm_version.strip()
    effective_parameters = parameters or ForecastObservationParameters()
    if not isinstance(effective_parameters, ForecastObservationParameters):
        raise ForecastObservationComparisonInputError(
            "invalid_forecast_observation_parameters"
        )

    digest = _source_digest(evidence, observation)
    identity = _comparison_id(
        observation=observation,
        source_digest=digest,
        algorithm_version=algorithm_version,
        parameters=effective_parameters,
    )
    provenance = _observation_provenance(observation)

    blocking_reasons = []
    if observation.legacy_lineage_incomplete:
        blocking_reasons.append(ComparisonReason("legacy_lineage_incomplete"))
    if QualityFlag.TIME_UNCERTAIN in observation.quality.flags:
        blocking_reasons.append(ComparisonReason("observation_time_uncertain"))
    if QualityFlag.LOCATION_UNCERTAIN in observation.quality.flags:
        blocking_reasons.append(
            ComparisonReason("observation_location_uncertain")
        )
    if blocking_reasons:
        return ForecastObservationComparison(
            comparison_id=identity,
            algorithm_version=algorithm_version,
            computed_at_utc=computed_at_utc,
            decision_id=observation.decision_id,
            observation_id=observation.observation_id,
            execution_id=observation.execution_id,
            source_digest=digest,
            parameters=effective_parameters,
            observation_provenance=provenance,
            results=(),
            status=ForecastObservationComparisonStatus.NOT_COMPARABLE,
            reasons=tuple(blocking_reasons),
        )

    evidence_reason = None
    if evidence is None:
        evidence_reason = "decision_forecast_evidence_missing"
    elif not _evidence_is_well_formed(evidence):
        evidence_reason = "decision_forecast_evidence_invalid"
    elif not evidence.forecast_points:
        evidence_reason = "decision_forecast_evidence_empty"

    observed_values = _observed_values(observation)
    results = []
    reasons = []
    if not observed_values:
        reasons.append(ComparisonReason("no_supported_observed_variables"))
    elif evidence_reason is not None:
        reasons.append(ComparisonReason(evidence_reason))
        for variable, _ in observed_values:
            result_reason = ComparisonReason(evidence_reason, variable)
            results.append(_not_comparable_result(variable, result_reason))
    else:
        assert isinstance(evidence, DecisionForecastEvidence)
        for variable, observed_value in observed_values:
            if (
                variable is WeatherVariable.CLOUD_COVER_PERCENT
                and observed_value is CloudState.UNKNOWN
            ):
                reason = ComparisonReason("observed_cloud_unknown", variable)
                results.append(_not_comparable_result(variable, reason))
                reasons.append(reason)
                continue
            point, selection_reason = _select_point(
                evidence,
                observation,
                variable,
                effective_parameters,
            )
            if selection_reason is not None:
                results.append(_not_comparable_result(variable, selection_reason))
                reasons.append(selection_reason)
                continue
            assert point is not None
            if variable is WeatherVariable.CLOUD_COVER_PERCENT:
                assert isinstance(observed_value, CloudState)
                results.append(
                    _cloud_result(
                        observed_condition=observed_value,
                        point=point,
                        observation=observation,
                    )
                )
            else:
                assert isinstance(observed_value, float)
                results.append(
                    _numeric_result(
                        variable=variable,
                        observed_value=observed_value,
                        point=point,
                        observation=observation,
                    )
                )

    result_tuple = tuple(results)
    return ForecastObservationComparison(
        comparison_id=identity,
        algorithm_version=algorithm_version,
        computed_at_utc=computed_at_utc,
        decision_id=observation.decision_id,
        observation_id=observation.observation_id,
        execution_id=observation.execution_id,
        source_digest=digest,
        parameters=effective_parameters,
        observation_provenance=provenance,
        results=result_tuple,
        status=_comparison_status(result_tuple),
        reasons=tuple(reasons),
    )
