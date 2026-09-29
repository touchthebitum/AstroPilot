from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol, TypeVar

from decision.field_observation import (
    CaptureMethod,
    CloudState,
    Confidence,
    ObservationSourceType,
    QualityFlag,
)
from decision.models.forecast_observation_comparison import (
    CloudComparisonOutcome,
    CloudMappingComparisonPolicy,
    CloudVariableComparison,
    ComparisonReason,
    ForecastObservationComparison,
    ForecastObservationComparisonStatus,
    ForecastObservationParameters,
    ForecastPointProvenance,
    NumericVariableComparison,
    ObservationComparisonProvenance,
    TemporalComparisonPolicy,
    VariableComparisonStatus,
)
from decision.models.outcome_assessment import (
    OutcomeAssessment,
    OutcomeAssessmentStatus,
    OutcomeFinding,
)
from decision.models.outcome_evaluation import (
    ForecastComparisonOutcomeEvidence,
    ForecastComparisonOutcomeEvidenceSourceType,
    OutcomeEvaluation,
)
from decision.weather.provider_reliability import WeatherVariable


SCHEMA_VERSION = 1
DOMAIN_VERSION = "outcome_evaluation.v1"


class OutcomeEvaluationPersistenceError(ValueError):
    pass


class OutcomeEvaluationStore(Protocol):
    def save(self, *, evaluation: OutcomeEvaluation) -> bool: ...
    def load(self, *, evaluation_id: str) -> OutcomeEvaluation | None: ...
    def list_by_observation(self, *, observation_id: str) -> list[OutcomeEvaluation]: ...
    def list_by_execution(self, *, execution_id: str) -> list[OutcomeEvaluation]: ...
    def list_by_comparison(self, *, comparison_id: str) -> list[OutcomeEvaluation]: ...


def _duration_us(value: timedelta) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _reason_document(reason: ComparisonReason) -> dict[str, object]:
    return {"code": reason.code, "variable": None if reason.variable is None else reason.variable.value}


def _point_document(point: ForecastPointProvenance | None) -> dict[str, object] | None:
    if point is None:
        return None
    return {
        "provider_id": point.provider_id,
        "model_id": point.model_id,
        "retrieved_at_utc": point.retrieved_at_utc.isoformat(),
        "forecast_for_utc": point.forecast_for_utc.isoformat(),
        "temporal_offset_us": _duration_us(point.temporal_offset),
    }


def _result_document(result: NumericVariableComparison | CloudVariableComparison) -> dict[str, object]:
    common = {
        "variable": result.variable.value,
        "status": result.status.value,
        "unit": result.unit,
        "forecast_point": _point_document(result.forecast_point),
        "reasons": [_reason_document(item) for item in result.reasons],
    }
    if type(result) is NumericVariableComparison:
        return {
            "result_type": "numeric",
            **common,
            "forecast_value": result.forecast_value,
            "observed_value": result.observed_value,
            "signed_error": result.signed_error,
            "absolute_error": result.absolute_error,
        }
    return {
        "result_type": "cloud",
        **common,
        "forecast_coverage_percent": result.forecast_coverage_percent,
        "predicted_condition": None if result.predicted_condition is None else result.predicted_condition.value,
        "observed_condition": None if result.observed_condition is None else result.observed_condition.value,
        "outcome": None if result.outcome is None else result.outcome.value,
        "confusion_cell": None if result.confusion_cell is None else [item.value for item in result.confusion_cell],
    }


def _comparison_document(value: ForecastObservationComparison) -> dict[str, object]:
    return {
        "comparison_id": value.comparison_id,
        "identity_persistable": value.identity_persistable,
        "computed_at_utc": value.computed_at_utc.isoformat(),
        "decision_id": value.decision_id,
        "observation_id": value.observation_id,
        "execution_id": value.execution_id,
        "source_digest": value.source_digest,
        "parameters": {
            "temporal_policy": {
                "version": value.parameters.temporal_policy.version,
                "maximum_absolute_offset_us": _duration_us(value.parameters.temporal_policy.maximum_absolute_offset),
                "timezone_name": value.parameters.temporal_policy.timezone_name,
                "selection_mode": value.parameters.temporal_policy.selection_mode,
                "interpolation_enabled": value.parameters.temporal_policy.interpolation_enabled,
                "averaging_enabled": value.parameters.temporal_policy.averaging_enabled,
            },
            "cloud_mapping_policy": {
                "version": value.parameters.cloud_mapping_policy.version,
                "boundaries_percent": list(value.parameters.cloud_mapping_policy.boundaries_percent),
            },
        },
        "observation_provenance": {
            "source_type": value.observation_provenance.source_type.value,
            "source_id": value.observation_provenance.source_id,
            "capture_method": value.observation_provenance.capture_method.value,
            "confidence": value.observation_provenance.confidence.value,
            "quality_flags": [item.value for item in value.observation_provenance.quality_flags],
        },
        "results": [_result_document(item) for item in value.results],
        "status": value.status.value,
        "reasons": [_reason_document(item) for item in value.reasons],
        "algorithm_version": value.algorithm_version,
        "forecast_scope": value.forecast_scope,
    }


def _evidence_document(value: ForecastComparisonOutcomeEvidence | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "evidence_id": value.evidence_id,
        "comparison_id": value.comparison_id,
        "decision_id": value.decision_id,
        "observation_id": value.observation_id,
        "execution_id": value.execution_id,
        "algorithm_version": value.algorithm_version,
        "derived_at_utc": value.derived_at_utc.isoformat(),
        "source_type": value.source_type.value,
    }


def _assessment_document(value: OutcomeAssessment | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "assessment_id": value.assessment_id,
        "execution_id": value.execution_id,
        "evidence_ids": list(value.evidence_ids),
        "assessed_at": value.assessed_at.isoformat(),
        "status": value.status.value,
        "findings": [
            {"finding_id": item.finding_id, "basis": item.basis, "evidence_ids": list(item.evidence_ids)}
            for item in value.findings
        ],
    }


def serialize_outcome_evaluation(evaluation: OutcomeEvaluation) -> str:
    if type(evaluation) is not OutcomeEvaluation:
        raise OutcomeEvaluationPersistenceError("invalid_outcome_evaluation")
    if not evaluation.comparison.identity_persistable:
        raise OutcomeEvaluationPersistenceError("comparison_identity_not_persistable")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "domain_version": DOMAIN_VERSION,
        "outcome_evaluation": {
            "evaluation_id": evaluation.evaluation_id,
            "evaluation_algorithm_version": evaluation.evaluation_algorithm_version,
            "comparison": _comparison_document(evaluation.comparison),
            "outcome_evidence": _evidence_document(evaluation.outcome_evidence),
            "assessment": _assessment_document(evaluation.assessment),
        },
    }
    try:
        return json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as error:
        raise OutcomeEvaluationPersistenceError("invalid_outcome_evaluation") from error


def _mapping(value: object, fields: frozenset[str], code: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OutcomeEvaluationPersistenceError(code)
    return value


def _list(value: object, code: str) -> list[object]:
    if type(value) is not list:
        raise OutcomeEvaluationPersistenceError(code)
    return value


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}") from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timedelta(0)
        or parsed.fold != 0
        or parsed.isoformat() != value
    ):
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}")
    return parsed


def _number(value: object, field: str, *, optional: bool = False) -> int | float | None:
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}")
    return value


def _digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}")
    return value


def _duration(value: object, field: str) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}")
    try:
        return timedelta(microseconds=value)
    except OverflowError as error:
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}") from error


E = TypeVar("E", bound=Enum)
def _enum(value: object, kind: type[E], field: str, optional: bool = False) -> E | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}")
    try:
        return kind(value)
    except ValueError as error:
        raise OutcomeEvaluationPersistenceError(f"invalid_{field}") from error


_REASON_FIELDS = frozenset(("code", "variable"))
_POINT_FIELDS = frozenset(("provider_id", "model_id", "retrieved_at_utc", "forecast_for_utc", "temporal_offset_us"))
_RESULT_COMMON = frozenset(("result_type", "variable", "status", "unit", "forecast_point", "reasons"))
_NUMERIC_FIELDS = _RESULT_COMMON | frozenset(("forecast_value", "observed_value", "signed_error", "absolute_error"))
_CLOUD_FIELDS = _RESULT_COMMON | frozenset(("forecast_coverage_percent", "predicted_condition", "observed_condition", "outcome", "confusion_cell"))


def _reason(value: object) -> ComparisonReason:
    item = _mapping(value, _REASON_FIELDS, "invalid_comparison_reason_fields")
    return ComparisonReason(code=item["code"], variable=_enum(item["variable"], WeatherVariable, "reason_variable", True))


def _point(value: object) -> ForecastPointProvenance | None:
    if value is None:
        return None
    item = _mapping(value, _POINT_FIELDS, "invalid_forecast_point_fields")
    return ForecastPointProvenance(
        provider_id=item["provider_id"], model_id=item["model_id"],
        retrieved_at_utc=_datetime(item["retrieved_at_utc"], "forecast_retrieved_at_utc"),
        forecast_for_utc=_datetime(item["forecast_for_utc"], "forecast_for_utc"),
        temporal_offset=_duration(item["temporal_offset_us"], "temporal_offset"),
    )


def _result(value: object) -> NumericVariableComparison | CloudVariableComparison:
    if not isinstance(value, Mapping):
        raise OutcomeEvaluationPersistenceError("invalid_result_fields")
    result_type = value.get("result_type")
    fields = _NUMERIC_FIELDS if result_type == "numeric" else _CLOUD_FIELDS if result_type == "cloud" else frozenset()
    item = _mapping(value, fields, "invalid_result_fields")
    common = dict(
        variable=_enum(item["variable"], WeatherVariable, "result_variable"),
        status=_enum(item["status"], VariableComparisonStatus, "result_status"),
        unit=item["unit"], forecast_point=_point(item["forecast_point"]),
        reasons=tuple(_reason(entry) for entry in _list(item["reasons"], "invalid_result_reasons")),
    )
    if result_type == "numeric":
        return NumericVariableComparison(
            **common,
            forecast_value=_number(item["forecast_value"], "forecast_value", optional=True),
            observed_value=_number(item["observed_value"], "observed_value", optional=True),
            signed_error=_number(item["signed_error"], "signed_error", optional=True),
            absolute_error=_number(item["absolute_error"], "absolute_error", optional=True),
        )
    cell = item["confusion_cell"]
    confusion_cell = None
    if cell is not None:
        values = _list(cell, "invalid_confusion_cell")
        if len(values) != 2:
            raise OutcomeEvaluationPersistenceError("invalid_confusion_cell")
        confusion_cell = tuple(_enum(entry, CloudState, "confusion_cell") for entry in values)
    return CloudVariableComparison(
        **common, forecast_coverage_percent=_number(item["forecast_coverage_percent"], "forecast_coverage_percent", optional=True),
        predicted_condition=_enum(item["predicted_condition"], CloudState, "predicted_condition", True),
        observed_condition=_enum(item["observed_condition"], CloudState, "observed_condition", True),
        outcome=_enum(item["outcome"], CloudComparisonOutcome, "cloud_outcome", True),
        confusion_cell=confusion_cell,
    )


_TEMPORAL_FIELDS = frozenset(("version", "maximum_absolute_offset_us", "timezone_name", "selection_mode", "interpolation_enabled", "averaging_enabled"))
_CLOUD_POLICY_FIELDS = frozenset(("version", "boundaries_percent"))
_PARAMETER_FIELDS = frozenset(("temporal_policy", "cloud_mapping_policy"))
_PROVENANCE_FIELDS = frozenset(("source_type", "source_id", "capture_method", "confidence", "quality_flags"))
_COMPARISON_FIELDS = frozenset(("comparison_id", "identity_persistable", "computed_at_utc", "decision_id", "observation_id", "execution_id", "source_digest", "parameters", "observation_provenance", "results", "status", "reasons", "algorithm_version", "forecast_scope"))


def _comparison(value: object) -> ForecastObservationComparison:
    item = _mapping(value, _COMPARISON_FIELDS, "invalid_comparison_fields")
    params = _mapping(item["parameters"], _PARAMETER_FIELDS, "invalid_parameter_fields")
    temporal = _mapping(params["temporal_policy"], _TEMPORAL_FIELDS, "invalid_temporal_policy_fields")
    cloud = _mapping(params["cloud_mapping_policy"], _CLOUD_POLICY_FIELDS, "invalid_cloud_policy_fields")
    boundaries = tuple(
        _number(entry, "cloud_boundary_percent")
        for entry in _list(cloud["boundaries_percent"], "invalid_cloud_boundaries")
    )
    provenance = _mapping(item["observation_provenance"], _PROVENANCE_FIELDS, "invalid_observation_provenance_fields")
    return ForecastObservationComparison(
        comparison_id=_digest(item["comparison_id"], "comparison_id"), identity_persistable=item["identity_persistable"],
        computed_at_utc=_datetime(item["computed_at_utc"], "computed_at_utc"), decision_id=item["decision_id"],
        observation_id=item["observation_id"], execution_id=item["execution_id"], source_digest=_digest(item["source_digest"], "source_digest"),
        parameters=ForecastObservationParameters(
            temporal_policy=TemporalComparisonPolicy(version=temporal["version"], maximum_absolute_offset=_duration(temporal["maximum_absolute_offset_us"], "maximum_absolute_offset"), timezone_name=temporal["timezone_name"], selection_mode=temporal["selection_mode"], interpolation_enabled=temporal["interpolation_enabled"], averaging_enabled=temporal["averaging_enabled"]),
            cloud_mapping_policy=CloudMappingComparisonPolicy(version=cloud["version"], boundaries_percent=boundaries),
        ),
        observation_provenance=ObservationComparisonProvenance(
            source_type=_enum(provenance["source_type"], ObservationSourceType, "observation_source_type"), source_id=provenance["source_id"],
            capture_method=_enum(provenance["capture_method"], CaptureMethod, "capture_method"), confidence=_enum(provenance["confidence"], Confidence, "confidence"),
            quality_flags=tuple(_enum(flag, QualityFlag, "quality_flag") for flag in _list(provenance["quality_flags"], "invalid_quality_flags")),
        ),
        results=tuple(_result(entry) for entry in _list(item["results"], "invalid_results")),
        status=_enum(item["status"], ForecastObservationComparisonStatus, "comparison_status"),
        reasons=tuple(_reason(entry) for entry in _list(item["reasons"], "invalid_comparison_reasons")),
        algorithm_version=item["algorithm_version"], forecast_scope=item["forecast_scope"],
    )


_EVIDENCE_FIELDS = frozenset(("evidence_id", "comparison_id", "decision_id", "observation_id", "execution_id", "algorithm_version", "derived_at_utc", "source_type"))
def _evidence(value: object) -> ForecastComparisonOutcomeEvidence | None:
    if value is None:
        return None
    item = _mapping(value, _EVIDENCE_FIELDS, "invalid_outcome_evidence_fields")
    return ForecastComparisonOutcomeEvidence(
        evidence_id=_digest(item["evidence_id"], "evidence_id"), comparison_id=_digest(item["comparison_id"], "comparison_id"), decision_id=item["decision_id"], observation_id=item["observation_id"], execution_id=item["execution_id"],
        algorithm_version=item["algorithm_version"], derived_at_utc=_datetime(item["derived_at_utc"], "derived_at_utc"), source_type=_enum(item["source_type"], ForecastComparisonOutcomeEvidenceSourceType, "outcome_evidence_source_type"),
    )


_FINDING_FIELDS = frozenset(("finding_id", "basis", "evidence_ids"))
_ASSESSMENT_FIELDS = frozenset(("assessment_id", "execution_id", "evidence_ids", "assessed_at", "status", "findings"))
def _assessment(value: object) -> OutcomeAssessment | None:
    if value is None:
        return None
    item = _mapping(value, _ASSESSMENT_FIELDS, "invalid_assessment_fields")
    evidence_ids = _list(item["evidence_ids"], "invalid_assessment_evidence_ids")
    findings = []
    for raw in _list(item["findings"], "invalid_findings"):
        finding = _mapping(raw, _FINDING_FIELDS, "invalid_finding_fields")
        findings.append(OutcomeFinding(finding_id=finding["finding_id"], basis=finding["basis"], evidence_ids=tuple(_list(finding["evidence_ids"], "invalid_finding_evidence_ids"))))
    return OutcomeAssessment(assessment_id=item["assessment_id"], execution_id=item["execution_id"], evidence_ids=tuple(evidence_ids), assessed_at=_datetime(item["assessed_at"], "assessed_at"), status=_enum(item["status"], OutcomeAssessmentStatus, "assessment_status"), findings=tuple(findings))


_ROOT_FIELDS = frozenset(("schema_version", "domain_version", "outcome_evaluation"))
_EVALUATION_FIELDS = frozenset(("evaluation_id", "evaluation_algorithm_version", "comparison", "outcome_evidence", "assessment"))
def _reject_constant(value: str):
    raise ValueError(value)


def deserialize_outcome_evaluation(document: str, *, evaluation_id: str | None = None) -> OutcomeEvaluation:
    if not isinstance(document, str):
        raise OutcomeEvaluationPersistenceError("invalid_json_document")
    try:
        payload = json.loads(document, parse_constant=_reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise OutcomeEvaluationPersistenceError("invalid_json_document") from error
    if not isinstance(payload, Mapping):
        raise OutcomeEvaluationPersistenceError("invalid_root_fields")
    if payload.get("schema_version") != SCHEMA_VERSION or type(payload.get("schema_version")) is not int:
        raise OutcomeEvaluationPersistenceError("invalid_schema_version")
    root = _mapping(payload, _ROOT_FIELDS, "invalid_root_fields")
    if root["domain_version"] != DOMAIN_VERSION:
        raise OutcomeEvaluationPersistenceError("invalid_domain_version")
    item = _mapping(root["outcome_evaluation"], _EVALUATION_FIELDS, "invalid_outcome_evaluation_fields")
    if evaluation_id is not None and item["evaluation_id"] != evaluation_id:
        raise OutcomeEvaluationPersistenceError("evaluation_id_mismatch")
    try:
        return OutcomeEvaluation(
            evaluation_id=_digest(item["evaluation_id"], "evaluation_id"), evaluation_algorithm_version=item["evaluation_algorithm_version"],
            comparison=_comparison(item["comparison"]), outcome_evidence=_evidence(item["outcome_evidence"]), assessment=_assessment(item["assessment"]),
        )
    except OutcomeEvaluationPersistenceError:
        raise
    except (TypeError, ValueError) as error:
        code = "comparison_identity_not_persistable" if str(error) == "comparison_identity_not_persistable" else "invalid_outcome_evaluation"
        raise OutcomeEvaluationPersistenceError(code) from error
