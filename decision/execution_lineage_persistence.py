from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    FieldOutcomeEvidence,
    ImageOutcomeEvidence,
    OutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)


SCHEMA_VERSION = 1
_IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_EXECUTION_TAG = "decision.models.execution.Execution"
_EVIDENCE_TAGS = {
    FieldOutcomeEvidence: "decision.models.outcome_evidence.FieldOutcomeEvidence",
    TechnicalOutcomeEvidence: (
        "decision.models.outcome_evidence.TechnicalOutcomeEvidence"
    ),
    AcquisitionOutcomeEvidence: (
        "decision.models.outcome_evidence.AcquisitionOutcomeEvidence"
    ),
    ImageOutcomeEvidence: "decision.models.outcome_evidence.ImageOutcomeEvidence",
}
_EVIDENCE_TYPES = {tag: kind for kind, tag in _EVIDENCE_TAGS.items()}


class ExecutionLineagePersistenceError(ValueError):
    pass


class ExecutionLineageNotFoundError(ExecutionLineagePersistenceError):
    pass


class ExecutionLineageConflictError(ExecutionLineagePersistenceError):
    pass


class ExecutionLineageStaleStateError(ExecutionLineageConflictError):
    pass


class ExecutionLineageCorruptionError(ExecutionLineagePersistenceError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionLineageAggregate:
    execution: Execution
    evidence: tuple[OutcomeEvidence, ...] = ()

    @property
    def execution_id(self) -> str:
        return self.execution.execution_id

    @property
    def mission_id(self) -> str:
        return self.execution.mission_id


def validate_lineage_identity(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _IDENTITY_PATTERN.fullmatch(value) is None:
        raise ExecutionLineageCorruptionError(f"invalid_{field}")
    return value


def _exact_mapping(value: object, fields: frozenset[str], code: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ExecutionLineageCorruptionError(code)
    return value


def _encode_datetime(value: datetime | None) -> dict | None:
    if value is None:
        return None
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ExecutionLineageCorruptionError("invalid_datetime")
    return {"$type": "datetime", "value": value.isoformat()}


def _decode_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    document = _exact_mapping(
        value, frozenset(("$type", "value")), "invalid_datetime_document"
    )
    if document["$type"] != "datetime" or not isinstance(document["value"], str):
        raise ExecutionLineageCorruptionError("invalid_datetime")
    try:
        result = datetime.fromisoformat(document["value"])
    except ValueError as error:
        raise ExecutionLineageCorruptionError("invalid_datetime") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ExecutionLineageCorruptionError("invalid_datetime")
    return result


def _duration_microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _encode_duration(value: timedelta | None) -> dict | None:
    if value is None:
        return None
    if type(value) is not timedelta:
        raise ExecutionLineageCorruptionError("invalid_timedelta")
    return {
        "$type": "timedelta",
        "microseconds": _duration_microseconds(value),
    }


def _decode_duration(value: object) -> timedelta | None:
    if value is None:
        return None
    document = _exact_mapping(
        value,
        frozenset(("$type", "microseconds")),
        "invalid_timedelta_document",
    )
    raw = document["microseconds"]
    if (
        document["$type"] != "timedelta"
        or isinstance(raw, bool)
        or not isinstance(raw, int)
    ):
        raise ExecutionLineageCorruptionError("invalid_timedelta")
    try:
        return timedelta(microseconds=raw)
    except OverflowError as error:
        raise ExecutionLineageCorruptionError("invalid_timedelta") from error


def _encode_enum(value, expected_type: type, tag: str) -> dict:
    if type(value) is not expected_type:
        raise ExecutionLineageCorruptionError(f"invalid_{tag}")
    return {"$type": tag, "value": value.value}


def _decode_enum(value: object, expected_type: type, tag: str):
    document = _exact_mapping(
        value, frozenset(("$type", "value")), f"invalid_{tag}_document"
    )
    if document["$type"] != tag:
        raise ExecutionLineageCorruptionError(f"invalid_{tag}")
    try:
        return expected_type(document["value"])
    except (TypeError, ValueError) as error:
        raise ExecutionLineageCorruptionError(f"invalid_{tag}") from error


def serialize_execution(execution: Execution) -> dict:
    if type(execution) is not Execution:
        raise ExecutionLineageCorruptionError("invalid_execution")
    return {
        "$type": _EXECUTION_TAG,
        "fields": {
            "execution_id": validate_lineage_identity(
                execution.execution_id, field="execution_id"
            ),
            "mission_id": validate_lineage_identity(
                execution.mission_id, field="mission_id"
            ),
            "status": _encode_enum(
                execution.status, ExecutionStatus, "execution_status"
            ),
            "actual_start": _encode_datetime(execution.actual_start),
            "actual_end": _encode_datetime(execution.actual_end),
            "actual_duration": _encode_duration(execution.actual_duration),
        },
    }


def deserialize_execution(document: object) -> Execution:
    typed = _exact_mapping(
        document, frozenset(("$type", "fields")), "invalid_execution_document"
    )
    if typed["$type"] != _EXECUTION_TAG:
        raise ExecutionLineageCorruptionError("unsupported_execution_type")
    values = _exact_mapping(
        typed["fields"],
        frozenset(
            (
                "execution_id",
                "mission_id",
                "status",
                "actual_start",
                "actual_end",
                "actual_duration",
            )
        ),
        "invalid_execution_fields",
    )
    try:
        return Execution(
            execution_id=validate_lineage_identity(
                values["execution_id"], field="execution_id"
            ),
            mission_id=validate_lineage_identity(
                values["mission_id"], field="mission_id"
            ),
            status=_decode_enum(
                values["status"], ExecutionStatus, "execution_status"
            ),
            actual_start=_decode_datetime(values["actual_start"]),
            actual_end=_decode_datetime(values["actual_end"]),
            actual_duration=_decode_duration(values["actual_duration"]),
        )
    except ExecutionLineagePersistenceError:
        raise
    except (TypeError, ValueError) as error:
        raise ExecutionLineageCorruptionError("invalid_execution") from error


def serialize_outcome_evidence(evidence: OutcomeEvidence) -> dict:
    tag = _EVIDENCE_TAGS.get(type(evidence))
    if tag is None:
        raise ExecutionLineageCorruptionError("unsupported_evidence_type")
    values = {
        "evidence_id": validate_lineage_identity(
            evidence.evidence_id, field="evidence_id"
        ),
        "execution_id": validate_lineage_identity(
            evidence.execution_id, field="execution_id"
        ),
        "category": _encode_enum(
            evidence.category, OutcomeEvidenceCategory, "outcome_evidence_category"
        ),
        "observed_at": _encode_datetime(evidence.observed_at),
        "source": _encode_enum(
            evidence.source, OutcomeEvidenceSource, "outcome_evidence_source"
        ),
    }
    if type(evidence) is AcquisitionOutcomeEvidence:
        values.update(
            actual_capture_duration=_encode_duration(
                evidence.actual_capture_duration
            ),
            usable_integration_duration=_encode_duration(
                evidence.usable_integration_duration
            ),
        )
    return {"$type": tag, "fields": values}


def deserialize_outcome_evidence(document: object) -> OutcomeEvidence:
    typed = _exact_mapping(
        document, frozenset(("$type", "fields")), "invalid_evidence_document"
    )
    kind = _EVIDENCE_TYPES.get(typed["$type"])
    if kind is None:
        raise ExecutionLineageCorruptionError("unsupported_evidence_type")
    expected_fields = {
        "evidence_id",
        "execution_id",
        "category",
        "observed_at",
        "source",
    }
    if kind is AcquisitionOutcomeEvidence:
        expected_fields.update(
            ("actual_capture_duration", "usable_integration_duration")
        )
    values = _exact_mapping(
        typed["fields"], frozenset(expected_fields), "invalid_evidence_fields"
    )
    arguments = {
        "evidence_id": validate_lineage_identity(
            values["evidence_id"], field="evidence_id"
        ),
        "execution_id": validate_lineage_identity(
            values["execution_id"], field="execution_id"
        ),
        "category": _decode_enum(
            values["category"],
            OutcomeEvidenceCategory,
            "outcome_evidence_category",
        ),
        "observed_at": _decode_datetime(values["observed_at"]),
        "source": _decode_enum(
            values["source"], OutcomeEvidenceSource, "outcome_evidence_source"
        ),
    }
    if kind is AcquisitionOutcomeEvidence:
        arguments.update(
            actual_capture_duration=_decode_duration(
                values["actual_capture_duration"]
            ),
            usable_integration_duration=_decode_duration(
                values["usable_integration_duration"]
            ),
        )
    try:
        return kind(**arguments)
    except ExecutionLineagePersistenceError:
        raise
    except (TypeError, ValueError) as error:
        raise ExecutionLineageCorruptionError("invalid_evidence") from error


def serialize_execution_lineage_aggregate(
    aggregate: ExecutionLineageAggregate,
) -> str:
    if type(aggregate) is not ExecutionLineageAggregate:
        raise ExecutionLineageCorruptionError("invalid_execution_aggregate")
    if type(aggregate.evidence) is not tuple or any(
        type(record) not in _EVIDENCE_TAGS for record in aggregate.evidence
    ):
        raise ExecutionLineageCorruptionError("invalid_evidence_collection")
    if any(record.execution_id != aggregate.execution_id for record in aggregate.evidence):
        raise ExecutionLineageCorruptionError("evidence_execution_mismatch")
    evidence_ids = tuple(record.evidence_id for record in aggregate.evidence)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ExecutionLineageCorruptionError("duplicate_evidence_id")
    document = {
        "schema_version": SCHEMA_VERSION,
        "execution_id": aggregate.execution_id,
        "mission_id": aggregate.mission_id,
        "execution": serialize_execution(aggregate.execution),
        "evidence": [
            serialize_outcome_evidence(record) for record in aggregate.evidence
        ],
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"


def deserialize_execution_lineage_aggregate(
    document: str,
    *,
    execution_id: str | None = None,
) -> ExecutionLineageAggregate:
    if not isinstance(document, str):
        raise ExecutionLineageCorruptionError("invalid_json_document")
    try:
        raw = json.loads(document)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ExecutionLineageCorruptionError("invalid_json_document") from error
    root = _exact_mapping(
        raw,
        frozenset(
            (
                "schema_version",
                "execution_id",
                "mission_id",
                "execution",
                "evidence",
            )
        ),
        "invalid_execution_aggregate",
    )
    if (
        type(root["schema_version"]) is not int
        or root["schema_version"] != SCHEMA_VERSION
    ):
        raise ExecutionLineageCorruptionError("unsupported_schema_version")
    root_execution_id = validate_lineage_identity(
        root["execution_id"], field="execution_id"
    )
    root_mission_id = validate_lineage_identity(root["mission_id"], field="mission_id")
    if execution_id is not None and root_execution_id != execution_id:
        raise ExecutionLineageCorruptionError("execution_identity_mismatch")
    restored_execution = deserialize_execution(root["execution"])
    if (
        restored_execution.execution_id != root_execution_id
        or restored_execution.mission_id != root_mission_id
    ):
        raise ExecutionLineageCorruptionError("execution_identity_mismatch")
    if type(root["evidence"]) is not list:
        raise ExecutionLineageCorruptionError("invalid_evidence_collection")
    restored_evidence = tuple(
        deserialize_outcome_evidence(item) for item in root["evidence"]
    )
    if any(item.execution_id != root_execution_id for item in restored_evidence):
        raise ExecutionLineageCorruptionError("evidence_execution_mismatch")
    evidence_ids = tuple(item.evidence_id for item in restored_evidence)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ExecutionLineageCorruptionError("duplicate_evidence_id")
    return ExecutionLineageAggregate(restored_execution, restored_evidence)
