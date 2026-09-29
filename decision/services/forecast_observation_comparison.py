from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
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
    WeatherLocation,
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
    if isinstance(value, float) and value == 0.0:
        return 0.0
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
            key=_canonical_json,
        ),
    }


def _deduplicate_identical_points(
    points: tuple[WeatherForecastPoint, ...],
) -> tuple[WeatherForecastPoint, ...]:
    unique = []
    identities = set()
    for point in points:
        identity = _canonical_json(_canonical_forecast_point(point))
        if identity in identities:
            continue
        identities.add(identity)
        unique.append(point)
    return tuple(unique)


class _InvalidEvidence(ValueError):
    def __init__(self, code: str, path: str, value: object) -> None:
        self.code = code
        self.path = path
        self.value = value
        super().__init__(code)


def _safe_fingerprint_token(
    value: object,
    *,
    seen: set[int] | None = None,
    depth: int = 0,
) -> dict:
    try:
        if value is None:
            return {"kind": "none"}
        if type(value) is str:
            encoded = value.encode("utf-8", errors="surrogatepass")
            return {
                "kind": "str",
                "digest": hashlib.sha256(encoded).hexdigest(),
            }
        if type(value) is bool:
            return {"kind": "bool", "value": value}
        if type(value) is int:
            byte_count = max(1, (value.bit_length() + 8) // 8)
            encoded = value.to_bytes(byte_count, "big", signed=True)
            return {
                "kind": "int",
                "digest": hashlib.sha256(encoded).hexdigest(),
            }
        if type(value) is float:
            return {"kind": "float", "digest": _digest(value.hex())}
        if isinstance(value, datetime):
            return {
                "kind": "datetime",
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "digest": _digest(
                    (
                        datetime.year.__get__(value, datetime),
                        datetime.month.__get__(value, datetime),
                        datetime.day.__get__(value, datetime),
                        datetime.hour.__get__(value, datetime),
                        datetime.minute.__get__(value, datetime),
                        datetime.second.__get__(value, datetime),
                        datetime.microsecond.__get__(value, datetime),
                        datetime.fold.__get__(value, datetime),
                        _safe_fingerprint_token(
                            datetime.tzinfo.__get__(value, datetime),
                            seen=seen,
                            depth=depth + 1,
                        ),
                    )
                ),
            }
        if isinstance(value, date):
            return {
                "kind": "date",
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "digest": _digest(
                    (
                        date.year.__get__(value, date),
                        date.month.__get__(value, date),
                        date.day.__get__(value, date),
                    )
                ),
            }
        if isinstance(value, time):
            return {
                "kind": "time",
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "digest": _digest(
                    (
                        time.hour.__get__(value, time),
                        time.minute.__get__(value, time),
                        time.second.__get__(value, time),
                        time.microsecond.__get__(value, time),
                        time.fold.__get__(value, time),
                        _safe_fingerprint_token(
                            time.tzinfo.__get__(value, time),
                            seen=seen,
                            depth=depth + 1,
                        ),
                    )
                ),
            }
        if isinstance(value, timedelta):
            return {
                "kind": "timedelta",
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "digest": _digest(
                    (
                        timedelta.days.__get__(value, timedelta),
                        timedelta.seconds.__get__(value, timedelta),
                        timedelta.microseconds.__get__(value, timedelta),
                    )
                ),
            }
        if type(value) is timezone:
            return {"kind": "timezone", "digest": _digest(str(value))}
        if type(value) is WeatherVariable:
            return {
                "kind": "weather_variable",
                "digest": _digest(value.value),
            }
        if depth >= 8:
            return {"kind": "depth_limit", "persistable": False}
        if seen is None:
            seen = set()
        identity = id(value)
        if identity in seen:
            return {"kind": "cycle", "persistable": False}
        if type(value) in (tuple, list):
            seen.add(identity)
            items = [
                _safe_fingerprint_token(item, seen=seen, depth=depth + 1)
                for item in value
            ]
            seen.remove(identity)
            return {"kind": type(value).__name__, "items": items}
        if type(value) is dict:
            seen.add(identity)
            entries = [
                {
                    "key": _safe_fingerprint_token(
                        key, seen=seen, depth=depth + 1
                    ),
                    "value": _safe_fingerprint_token(
                        item, seen=seen, depth=depth + 1
                    ),
                }
                for key, item in dict.items(value)
            ]
            seen.remove(identity)
            entries.sort(key=_canonical_json)
            return {"kind": "dict", "entries": entries}
        if type(value) in (set, frozenset):
            seen.add(identity)
            items = [
                _safe_fingerprint_token(item, seen=seen, depth=depth + 1)
                for item in value
            ]
            seen.remove(identity)
            items.sort(key=_canonical_json)
            return {"kind": type(value).__name__, "items": items}
        if type(value) in (bytes, bytearray):
            return {
                "kind": type(value).__name__,
                "digest": hashlib.sha256(bytes(value)).hexdigest(),
            }
        if type(value) in (
            DecisionForecastEvidence,
            WeatherForecastPoint,
            WeatherLocation,
            WeatherValue,
        ):
            seen.add(identity)
            attributes = object.__getattribute__(value, "__dict__")
            fields = {
                key: _safe_fingerprint_token(
                    attributes[key], seen=seen, depth=depth + 1
                )
                for key in sorted(attributes)
                if type(key) is str
            }
            seen.remove(identity)
            return {"kind": type(value).__name__, "fields": fields}
        try:
            attributes = object.__getattribute__(value, "__dict__")
        except Exception:
            attributes = None
        if type(attributes) is dict and attributes:
            seen.add(identity)
            token = _safe_fingerprint_token(
                attributes, seen=seen, depth=depth + 1
            )
            seen.remove(identity)
            return {
                "kind": "object",
                "type": f"{type(value).__module__}.{type(value).__qualname__}",
                "attributes": token,
            }
        return {
            "kind": "opaque",
            "type": f"{type(value).__module__}.{type(value).__qualname__}",
            "persistable": False,
        }
    except Exception:
        return {"kind": "unavailable", "persistable": False}


def _fingerprint_is_persistable(value: object) -> bool:
    if type(value) is dict:
        if value.get("persistable") is False:
            return False
        return all(_fingerprint_is_persistable(item) for item in value.values())
    if type(value) in (tuple, list):
        return all(_fingerprint_is_persistable(item) for item in value)
    return True


def _record_inspected_value(
    context: dict,
    fingerprint_parts: list[dict],
    path: str,
    value: object,
) -> object:
    context["path"] = path
    context["value"] = value
    fingerprint_parts.append(
        {"path": path, "value": _safe_fingerprint_token(value)}
    )
    return value


def _require_evidence_invariant(
    condition: bool,
    code: str,
    path: str,
    value: object,
) -> None:
    if not condition:
        raise _InvalidEvidence(code, path, value)


def _validated_location(
    location: object,
    *,
    path: str,
    context: dict,
    fingerprint_parts: list[dict],
) -> WeatherLocation:
    _require_evidence_invariant(
        type(location) is WeatherLocation,
        "invalid_location_type",
        path,
        location,
    )
    latitude = _record_inspected_value(
        context, fingerprint_parts, f"{path}.latitude", location.latitude
    )
    longitude = _record_inspected_value(
        context, fingerprint_parts, f"{path}.longitude", location.longitude
    )
    altitude_m = _record_inspected_value(
        context, fingerprint_parts, f"{path}.altitude_m", location.altitude_m
    )
    _require_evidence_invariant(
        type(latitude) is float,
        "non_canonical_latitude",
        f"{path}.latitude",
        latitude,
    )
    _require_evidence_invariant(
        type(longitude) is float,
        "non_canonical_longitude",
        f"{path}.longitude",
        longitude,
    )
    _require_evidence_invariant(
        altitude_m is None or type(altitude_m) is float,
        "non_canonical_altitude",
        f"{path}.altitude_m",
        altitude_m,
    )
    rebuilt = WeatherLocation(latitude, longitude, altitude_m=altitude_m)
    _require_evidence_invariant(
        rebuilt == location,
        "location_invariant_mismatch",
        path,
        location,
    )
    return rebuilt


def _validated_weather_value(
    value: object,
    *,
    path: str,
    context: dict,
    fingerprint_parts: list[dict],
) -> WeatherValue:
    _require_evidence_invariant(
        type(value) is WeatherValue,
        "invalid_weather_value_type",
        path,
        value,
    )
    variable = _record_inspected_value(
        context, fingerprint_parts, f"{path}.variable", value.variable
    )
    numeric_value = _record_inspected_value(
        context, fingerprint_parts, f"{path}.value", value.value
    )
    unit = _record_inspected_value(
        context, fingerprint_parts, f"{path}.unit", value.unit
    )
    aggregation_period = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.aggregation_period",
        value.aggregation_period,
    )
    _require_evidence_invariant(
        type(variable) is WeatherVariable,
        "invalid_weather_variable",
        f"{path}.variable",
        variable,
    )
    _require_evidence_invariant(
        type(numeric_value) is float,
        "non_canonical_weather_value",
        f"{path}.value",
        numeric_value,
    )
    _require_evidence_invariant(
        type(unit) is str,
        "non_canonical_weather_unit",
        f"{path}.unit",
        unit,
    )
    _require_evidence_invariant(
        unit == CANONICAL_UNITS[variable],
        "non_canonical_weather_unit",
        f"{path}.unit",
        unit,
    )
    _require_evidence_invariant(
        aggregation_period is None or type(aggregation_period) is timedelta,
        "non_canonical_aggregation_period",
        f"{path}.aggregation_period",
        aggregation_period,
    )
    rebuilt = WeatherValue(
        variable=variable,
        value=numeric_value,
        unit=unit,
        aggregation_period=aggregation_period,
    )
    _require_evidence_invariant(
        rebuilt == value,
        "weather_value_invariant_mismatch",
        path,
        value,
    )
    return rebuilt


def _validated_forecast_point(
    point: object,
    *,
    index: int,
    context: dict,
    fingerprint_parts: list[dict],
) -> WeatherForecastPoint:
    path = f"forecast_points[{index}]"
    _require_evidence_invariant(
        type(point) is WeatherForecastPoint,
        "invalid_forecast_point_type",
        path,
        point,
    )
    provider_id = _record_inspected_value(
        context, fingerprint_parts, f"{path}.provider_id", point.provider_id
    )
    model_id = _record_inspected_value(
        context, fingerprint_parts, f"{path}.model_id", point.model_id
    )
    retrieved_at_utc = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.retrieved_at_utc",
        point.retrieved_at_utc,
    )
    forecast_for_utc = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.forecast_for_utc",
        point.forecast_for_utc,
    )
    requested_location = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.requested_location",
        point.requested_location,
    )
    grid_location = _record_inspected_value(
        context,
        fingerprint_parts,
        f"{path}.grid_location",
        point.grid_location,
    )
    values = _record_inspected_value(
        context, fingerprint_parts, f"{path}.values", point.values
    )
    _require_evidence_invariant(
        type(provider_id) is str,
        "non_canonical_provider_id",
        f"{path}.provider_id",
        provider_id,
    )
    _require_evidence_invariant(
        bool(provider_id) and provider_id == provider_id.strip(),
        "non_canonical_provider_id",
        f"{path}.provider_id",
        provider_id,
    )
    _require_evidence_invariant(
        model_id is None or type(model_id) is str,
        "non_canonical_model_id",
        f"{path}.model_id",
        model_id,
    )
    _require_evidence_invariant(
        model_id is None or (bool(model_id) and model_id == model_id.strip()),
        "non_canonical_model_id",
        f"{path}.model_id",
        model_id,
    )
    _require_evidence_invariant(
        type(retrieved_at_utc) is datetime,
        "non_canonical_retrieved_at_utc",
        f"{path}.retrieved_at_utc",
        retrieved_at_utc,
    )
    _require_evidence_invariant(
        type(forecast_for_utc) is datetime,
        "non_canonical_forecast_for_utc",
        f"{path}.forecast_for_utc",
        forecast_for_utc,
    )
    _require_evidence_invariant(
        type(values) is tuple,
        "non_canonical_forecast_values",
        f"{path}.values",
        values,
    )
    _require_evidence_invariant(
        bool(values),
        "forecast_values_required",
        f"{path}.values",
        values,
    )
    rebuilt_requested_location = _validated_location(
        requested_location,
        path=f"{path}.requested_location",
        context=context,
        fingerprint_parts=fingerprint_parts,
    )
    rebuilt_grid_location = _validated_location(
        grid_location,
        path=f"{path}.grid_location",
        context=context,
        fingerprint_parts=fingerprint_parts,
    )
    rebuilt_values = tuple(
        _validated_weather_value(
            value,
            path=f"{path}.values[{value_index}]",
            context=context,
            fingerprint_parts=fingerprint_parts,
        )
        for value_index, value in enumerate(values)
    )
    context["path"] = path
    context["value"] = point
    rebuilt = WeatherForecastPoint(
        provider_id=provider_id,
        model_id=model_id,
        retrieved_at_utc=retrieved_at_utc,
        forecast_for_utc=forecast_for_utc,
        requested_location=rebuilt_requested_location,
        grid_location=rebuilt_grid_location,
        values=rebuilt_values,
    )
    _require_evidence_invariant(
        rebuilt == point
        and _canonical_datetime(rebuilt.retrieved_at_utc)
        == _canonical_datetime(retrieved_at_utc)
        and _canonical_datetime(rebuilt.forecast_for_utc)
        == _canonical_datetime(forecast_for_utc),
        "forecast_point_invariant_mismatch",
        path,
        point,
    )
    return rebuilt


def _invalid_evidence_document(
    *,
    code: str,
    path: str,
    value: object,
    fingerprint_parts: list[dict],
) -> dict:
    fingerprint_document = {
        "inspected": fingerprint_parts,
        "failure": {
            "path": path,
            "value": _safe_fingerprint_token(value),
        },
    }
    return {
        "state": "invalid",
        "invalid_reason_code": code,
        "invalid_path": path,
        "invalid_identity_persistable": _fingerprint_is_persistable(
            fingerprint_document
        ),
        "invalid_fingerprint": _digest(fingerprint_document),
    }


def _inspect_evidence(evidence: object) -> tuple[bool, dict]:
    if evidence is None:
        return False, {"state": "missing"}
    fingerprint_parts: list[dict] = []
    context = {"path": "evidence", "value": evidence}
    try:
        _require_evidence_invariant(
            type(evidence) is DecisionForecastEvidence,
            "invalid_evidence_type",
            "evidence",
            evidence,
        )
        points = _record_inspected_value(
            context,
            fingerprint_parts,
            "forecast_points",
            evidence.forecast_points,
        )
        _require_evidence_invariant(
            type(points) is tuple,
            "non_canonical_forecast_points",
            "forecast_points",
            points,
        )
        rebuilt_points = tuple(
            _validated_forecast_point(
                point,
                index=index,
                context=context,
                fingerprint_parts=fingerprint_parts,
            )
            for index, point in enumerate(points)
        )
        context["path"] = "evidence"
        context["value"] = evidence
        rebuilt_evidence = DecisionForecastEvidence(rebuilt_points)
        _require_evidence_invariant(
            rebuilt_evidence == evidence,
            "evidence_invariant_mismatch",
            "evidence",
            evidence,
        )
        unique_points = _deduplicate_identical_points(rebuilt_points)
        documents = [_canonical_forecast_point(point) for point in unique_points]
        documents.sort(key=_canonical_json)
        return True, {"state": "present", "forecast_points": documents}
    except Exception as error:
        if isinstance(error, _InvalidEvidence):
            code = error.code
            path = error.path
            value = error.value
        else:
            code = "evidence_inspection_failed"
            path = context["path"]
            value = context["value"]
        return False, _invalid_evidence_document(
            code=code,
            path=path,
            value=value,
            fingerprint_parts=fingerprint_parts,
        )


def _canonical_evidence(evidence: object) -> dict:
    return _inspect_evidence(evidence)[1]


def _evidence_is_well_formed(evidence: object) -> bool:
    return _inspect_evidence(evidence)[0]


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
    canonical_evidence: dict,
    observation: FieldObservation,
) -> str:
    return _digest(
        {
            "decision_forecast_evidence": canonical_evidence,
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

    evidence_is_well_formed, canonical_evidence = _inspect_evidence(evidence)
    digest = _source_digest(canonical_evidence, observation)
    identity = _comparison_id(
        observation=observation,
        source_digest=digest,
        algorithm_version=algorithm_version,
        parameters=effective_parameters,
    )
    provenance = _observation_provenance(observation)

    evidence_reason = None
    if evidence is None:
        evidence_reason = "decision_forecast_evidence_missing"
    elif not evidence_is_well_formed:
        evidence_reason = "decision_forecast_evidence_invalid"
    elif not evidence.forecast_points:
        evidence_reason = "decision_forecast_evidence_empty"

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
        if evidence_reason == "decision_forecast_evidence_invalid":
            blocking_reasons.insert(0, ComparisonReason(evidence_reason))
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

    observed_values = _observed_values(observation)
    results = []
    reasons = []
    if not observed_values:
        if evidence_reason == "decision_forecast_evidence_invalid":
            reasons.append(ComparisonReason(evidence_reason))
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
