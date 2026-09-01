from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from decision.execution_record import (
    ExecutionRecord,
    validate_execution_identity,
)


SCHEMA_VERSION = 1
_ROOT_FIELDS = frozenset(("schema_version", "execution"))
_EXECUTION_FIELDS = frozenset(
    (
        "execution_id",
        "decision_id",
        "started_at_utc",
        "ended_at_utc",
        "object",
        "hours",
        "filter_type",
    )
)


class ExecutionRecordPersistenceError(ValueError):
    pass


class ExecutionRecordStore(Protocol):
    def save(self, *, execution: ExecutionRecord) -> None: ...

    def load(self, *, execution_id: str) -> ExecutionRecord | None: ...


def serialize_execution_record(execution: ExecutionRecord) -> str:
    if not isinstance(execution, ExecutionRecord):
        raise ExecutionRecordPersistenceError("invalid_execution_record")
    document = {
        "schema_version": SCHEMA_VERSION,
        "execution": {
            "execution_id": execution.execution_id,
            "decision_id": execution.decision_id,
            "started_at_utc": execution.started_at_utc.isoformat(),
            "ended_at_utc": execution.ended_at_utc.isoformat(),
            "object": execution.object,
            "hours": execution.hours,
            "filter_type": execution.filter_type,
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
        raise ExecutionRecordPersistenceError(
            "invalid_execution_record"
        ) from error


def _mapping(
    value: object,
    *,
    fields: frozenset[str],
    code: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ExecutionRecordPersistenceError(code)
    return value


def _datetime(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ExecutionRecordPersistenceError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ExecutionRecordPersistenceError(f"invalid_{field}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionRecordPersistenceError(f"invalid_{field}")
    return parsed


def _reject_json_constant(value: str):
    raise ValueError(f"invalid_json_constant:{value}")


def deserialize_execution_record(
    document: str,
    *,
    execution_id: str,
) -> ExecutionRecord:
    try:
        identity = validate_execution_identity(
            execution_id,
            field="execution_id",
        )
    except ValueError as error:
        raise ExecutionRecordPersistenceError("invalid_execution_id") from error
    if not isinstance(document, str):
        raise ExecutionRecordPersistenceError("invalid_json_document")
    try:
        payload = json.loads(document, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ExecutionRecordPersistenceError("invalid_json_document") from error

    if not isinstance(payload, Mapping):
        raise ExecutionRecordPersistenceError("invalid_root_fields")
    if "schema_version" not in payload:
        raise ExecutionRecordPersistenceError("invalid_schema_version")
    root = _mapping(payload, fields=_ROOT_FIELDS, code="invalid_root_fields")
    version = root["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ExecutionRecordPersistenceError("invalid_schema_version")
    execution_document = _mapping(
        root["execution"],
        fields=_EXECUTION_FIELDS,
        code="invalid_execution_fields",
    )
    stored_identity = execution_document["execution_id"]
    try:
        validate_execution_identity(stored_identity, field="execution_id")
    except ValueError as error:
        raise ExecutionRecordPersistenceError("invalid_execution_id") from error
    if stored_identity != identity:
        raise ExecutionRecordPersistenceError("execution_id_mismatch")

    try:
        return ExecutionRecord(
            execution_id=stored_identity,
            decision_id=execution_document["decision_id"],
            started_at_utc=_datetime(
                execution_document["started_at_utc"],
                field="started_at_utc",
            ),
            ended_at_utc=_datetime(
                execution_document["ended_at_utc"],
                field="ended_at_utc",
            ),
            object=execution_document["object"],
            hours=execution_document["hours"],
            filter_type=execution_document["filter_type"],
        )
    except (TypeError, ValueError) as error:
        raise ExecutionRecordPersistenceError("invalid_execution_record") from error
