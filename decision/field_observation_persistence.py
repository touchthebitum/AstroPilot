from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from decision.execution_record import validate_execution_identity
from decision.field_observation import (
    CloudCondition,
    FieldObservation,
    SeeingCondition,
    Transparency,
)


SCHEMA_VERSION = 1
_ROOT_FIELDS = frozenset(("schema_version", "observation"))
_OBSERVATION_FIELDS = frozenset(
    (
        "observation_id",
        "execution_id",
        "observed_at_utc",
        "cloud_condition",
        "transparency",
        "seeing",
        "dew_detected",
    )
)


class FieldObservationPersistenceError(ValueError):
    pass


class FieldObservationStore(Protocol):
    def save(self, *, observation: FieldObservation) -> None: ...

    def load(
        self,
        *,
        observation_id: str,
    ) -> FieldObservation | None: ...


def serialize_field_observation(observation: FieldObservation) -> str:
    if not isinstance(observation, FieldObservation):
        raise FieldObservationPersistenceError("invalid_field_observation")
    document = {
        "schema_version": SCHEMA_VERSION,
        "observation": {
            "observation_id": observation.observation_id,
            "execution_id": observation.execution_id,
            "observed_at_utc": observation.observed_at_utc.isoformat(),
            "cloud_condition": (
                observation.cloud_condition.value
                if observation.cloud_condition is not None
                else None
            ),
            "transparency": (
                observation.transparency.value
                if observation.transparency is not None
                else None
            ),
            "seeing": (
                observation.seeing.value
                if observation.seeing is not None
                else None
            ),
            "dew_detected": observation.dew_detected,
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
        raise FieldObservationPersistenceError(
            "invalid_field_observation"
        ) from error


def _mapping(
    value: object,
    *,
    fields: frozenset[str],
    code: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise FieldObservationPersistenceError(code)
    return value


def _datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise FieldObservationPersistenceError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise FieldObservationPersistenceError(f"invalid_{field}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FieldObservationPersistenceError(f"invalid_{field}")
    return parsed


def _enum(value: object, enum_type: type[EnumValue], *, field: str):
    if value is None:
        return None
    if not isinstance(value, str):
        raise FieldObservationPersistenceError(f"invalid_{field}")
    try:
        return enum_type(value)
    except ValueError as error:
        raise FieldObservationPersistenceError(f"invalid_{field}") from error


EnumValue = CloudCondition | Transparency | SeeingCondition


def _reject_json_constant(value: str):
    raise ValueError(f"invalid_json_constant:{value}")


def deserialize_field_observation(
    document: str,
    *,
    observation_id: str,
) -> FieldObservation:
    try:
        identity = validate_execution_identity(
            observation_id,
            field="observation_id",
        )
    except ValueError as error:
        raise FieldObservationPersistenceError(
            "invalid_observation_id"
        ) from error
    if not isinstance(document, str):
        raise FieldObservationPersistenceError("invalid_json_document")
    try:
        payload = json.loads(document, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise FieldObservationPersistenceError(
            "invalid_json_document"
        ) from error

    if not isinstance(payload, Mapping):
        raise FieldObservationPersistenceError("invalid_root_fields")
    if "schema_version" not in payload:
        raise FieldObservationPersistenceError("invalid_schema_version")
    root = _mapping(payload, fields=_ROOT_FIELDS, code="invalid_root_fields")
    version = root["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise FieldObservationPersistenceError("invalid_schema_version")
    observation_document = _mapping(
        root["observation"],
        fields=_OBSERVATION_FIELDS,
        code="invalid_observation_fields",
    )
    stored_identity = observation_document["observation_id"]
    try:
        validate_execution_identity(stored_identity, field="observation_id")
    except ValueError as error:
        raise FieldObservationPersistenceError(
            "invalid_observation_id"
        ) from error
    if stored_identity != identity:
        raise FieldObservationPersistenceError("observation_id_mismatch")

    try:
        return FieldObservation(
            observation_id=stored_identity,
            execution_id=observation_document["execution_id"],
            observed_at_utc=_datetime(
                observation_document["observed_at_utc"],
                field="observed_at_utc",
            ),
            cloud_condition=_enum(
                observation_document["cloud_condition"],
                CloudCondition,
                field="cloud_condition",
            ),
            transparency=_enum(
                observation_document["transparency"],
                Transparency,
                field="transparency",
            ),
            seeing=_enum(
                observation_document["seeing"],
                SeeingCondition,
                field="seeing",
            ),
            dew_detected=observation_document["dew_detected"],
        )
    except FieldObservationPersistenceError:
        raise
    except (TypeError, ValueError) as error:
        raise FieldObservationPersistenceError(
            "invalid_field_observation"
        ) from error
