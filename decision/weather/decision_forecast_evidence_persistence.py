from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol

from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


SCHEMA_VERSION = 1
_DECISION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_ROOT_FIELDS = frozenset(("schema_version", "decision_id", "forecast_evidence"))
_EVIDENCE_FIELDS = frozenset(("forecast_points",))
_FORECAST_POINT_FIELDS = frozenset(
    (
        "provider_id",
        "model_id",
        "retrieved_at_utc",
        "forecast_for_utc",
        "requested_location",
        "grid_location",
        "values",
    )
)
_LOCATION_FIELDS = frozenset(("latitude", "longitude", "altitude_m"))
_VALUE_FIELDS = frozenset(
    ("variable", "value", "unit", "aggregation_period_us")
)


class DecisionForecastEvidencePersistenceError(ValueError):
    pass


class DecisionForecastEvidenceStore(Protocol):
    def save(
        self,
        *,
        decision_id: str,
        evidence: DecisionForecastEvidence,
    ) -> None: ...

    def load(
        self,
        *,
        decision_id: str,
    ) -> DecisionForecastEvidence | None: ...


def validate_decision_id(decision_id: object) -> str:
    if not isinstance(decision_id, str) or _DECISION_ID_PATTERN.fullmatch(
        decision_id
    ) is None:
        raise DecisionForecastEvidencePersistenceError("invalid_decision_id")
    return decision_id


def _datetime_document(value: datetime) -> str:
    return value.isoformat()


def _duration_document(value: timedelta | None) -> int | None:
    if value is None:
        return None
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _location_document(location: WeatherLocation) -> dict[str, object]:
    return {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "altitude_m": location.altitude_m,
    }


def _value_document(value: WeatherValue) -> dict[str, object]:
    return {
        "variable": value.variable.value,
        "value": value.value,
        "unit": value.unit,
        "aggregation_period_us": _duration_document(value.aggregation_period),
    }


def _forecast_point_document(point: WeatherForecastPoint) -> dict[str, object]:
    return {
        "provider_id": point.provider_id,
        "model_id": point.model_id,
        "retrieved_at_utc": _datetime_document(point.retrieved_at_utc),
        "forecast_for_utc": _datetime_document(point.forecast_for_utc),
        "requested_location": _location_document(point.requested_location),
        "grid_location": _location_document(point.grid_location),
        "values": [_value_document(value) for value in point.values],
    }


def serialize_decision_forecast_evidence(
    *,
    decision_id: str,
    evidence: DecisionForecastEvidence,
) -> str:
    identity = validate_decision_id(decision_id)
    if not isinstance(evidence, DecisionForecastEvidence):
        raise DecisionForecastEvidencePersistenceError(
            "invalid_decision_forecast_evidence"
        )
    document = {
        "schema_version": SCHEMA_VERSION,
        "decision_id": identity,
        "forecast_evidence": {
            "forecast_points": [
                _forecast_point_document(point)
                for point in evidence.forecast_points
            ]
        },
    }
    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise DecisionForecastEvidencePersistenceError(
            "invalid_decision_forecast_evidence"
        ) from error


def _mapping(
    value: object,
    *,
    fields: frozenset[str],
    code: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DecisionForecastEvidencePersistenceError(code)
    return value


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise DecisionForecastEvidencePersistenceError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise DecisionForecastEvidencePersistenceError(
            f"invalid_{field}"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DecisionForecastEvidencePersistenceError(f"invalid_{field}")
    return parsed


def _location(value: object) -> WeatherLocation:
    document = _mapping(
        value,
        fields=_LOCATION_FIELDS,
        code="invalid_location_fields",
    )
    try:
        return WeatherLocation(
            latitude=document["latitude"],
            longitude=document["longitude"],
            altitude_m=document["altitude_m"],
        )
    except (TypeError, ValueError) as error:
        raise DecisionForecastEvidencePersistenceError("invalid_location") from error


def _aggregation_period(value: object) -> timedelta | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise DecisionForecastEvidencePersistenceError(
            "invalid_aggregation_period"
        )
    try:
        return timedelta(microseconds=value)
    except OverflowError as error:
        raise DecisionForecastEvidencePersistenceError(
            "invalid_aggregation_period"
        ) from error


def _weather_value(value: object) -> WeatherValue:
    document = _mapping(
        value,
        fields=_VALUE_FIELDS,
        code="invalid_weather_value_fields",
    )
    variable_value = document["variable"]
    if not isinstance(variable_value, str):
        raise DecisionForecastEvidencePersistenceError("invalid_weather_variable")
    try:
        variable = WeatherVariable(variable_value)
    except ValueError as error:
        raise DecisionForecastEvidencePersistenceError(
            "invalid_weather_variable"
        ) from error
    try:
        return WeatherValue(
            variable=variable,
            value=document["value"],
            unit=document["unit"],
            aggregation_period=_aggregation_period(
                document["aggregation_period_us"]
            ),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, DecisionForecastEvidencePersistenceError):
            raise
        raise DecisionForecastEvidencePersistenceError(
            "invalid_weather_value"
        ) from error


def _forecast_point(value: object) -> WeatherForecastPoint:
    document = _mapping(
        value,
        fields=_FORECAST_POINT_FIELDS,
        code="invalid_forecast_point_fields",
    )
    values = document["values"]
    if not isinstance(values, list):
        raise DecisionForecastEvidencePersistenceError("invalid_forecast_values")
    try:
        return WeatherForecastPoint(
            provider_id=document["provider_id"],
            model_id=document["model_id"],
            retrieved_at_utc=_datetime(
                document["retrieved_at_utc"], "retrieved_at_utc"
            ),
            forecast_for_utc=_datetime(
                document["forecast_for_utc"], "forecast_for_utc"
            ),
            requested_location=_location(document["requested_location"]),
            grid_location=_location(document["grid_location"]),
            values=tuple(_weather_value(item) for item in values),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, DecisionForecastEvidencePersistenceError):
            raise
        raise DecisionForecastEvidencePersistenceError(
            "invalid_forecast_point"
        ) from error


def _reject_json_constant(value: str):
    raise ValueError(f"invalid_json_constant:{value}")


def deserialize_decision_forecast_evidence(
    document: str,
    *,
    decision_id: str,
) -> DecisionForecastEvidence:
    identity = validate_decision_id(decision_id)
    if not isinstance(document, str):
        raise DecisionForecastEvidencePersistenceError("invalid_json_document")
    try:
        payload = json.loads(document, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise DecisionForecastEvidencePersistenceError(
            "invalid_json_document"
        ) from error
    if not isinstance(payload, Mapping):
        raise DecisionForecastEvidencePersistenceError("invalid_root_fields")
    if "schema_version" not in payload:
        raise DecisionForecastEvidencePersistenceError("invalid_schema_version")
    root = _mapping(payload, fields=_ROOT_FIELDS, code="invalid_root_fields")
    version = root["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise DecisionForecastEvidencePersistenceError("invalid_schema_version")
    stored_identity = root["decision_id"]
    validate_decision_id(stored_identity)
    if stored_identity != identity:
        raise DecisionForecastEvidencePersistenceError("decision_id_mismatch")
    evidence_document = _mapping(
        root["forecast_evidence"],
        fields=_EVIDENCE_FIELDS,
        code="invalid_forecast_evidence_fields",
    )
    points = evidence_document["forecast_points"]
    if not isinstance(points, list):
        raise DecisionForecastEvidencePersistenceError("invalid_forecast_points")
    try:
        return DecisionForecastEvidence(tuple(_forecast_point(item) for item in points))
    except (TypeError, ValueError) as error:
        if isinstance(error, DecisionForecastEvidencePersistenceError):
            raise
        raise DecisionForecastEvidencePersistenceError(
            "invalid_decision_forecast_evidence"
        ) from error
