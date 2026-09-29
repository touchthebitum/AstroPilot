from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from decision.models.forecast_observation_comparison import (
    ForecastObservationComparison,
)
from decision.models.outcome_assessment import OutcomeAssessment


OUTCOME_EVALUATION_ALGORITHM_VERSION = "outcome_evaluation.v1"
FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION = (
    "forecast_comparison_outcome_evidence.v1"
)
_EVALUATION_AGGREGATE_TYPE = "OutcomeEvaluation"
_EVIDENCE_TYPE = "ForecastComparisonOutcomeEvidence"


class ForecastComparisonOutcomeEvidenceSourceType(str, Enum):
    SYSTEM_DERIVED = "system_derived"


OutcomeEvidenceSourceType = ForecastComparisonOutcomeEvidenceSourceType


def _canonical_digest(value: dict[str, str]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_outcome_evaluation_id(
    *,
    comparison_id: str,
    evaluation_algorithm_version: str = OUTCOME_EVALUATION_ALGORITHM_VERSION,
) -> str:
    return _canonical_digest(
        {
            "aggregate_type": _EVALUATION_AGGREGATE_TYPE,
            "comparison_id": comparison_id,
            "evaluation_algorithm_version": evaluation_algorithm_version,
        }
    )


def derive_forecast_comparison_outcome_evidence_id(
    *,
    evaluation_id: str,
    comparison_id: str,
    decision_id: str,
    observation_id: str,
    execution_id: str,
    algorithm_version: str = (
        FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION
    ),
) -> str:
    return _canonical_digest(
        {
            "evidence_type": _EVIDENCE_TYPE,
            "evaluation_id": evaluation_id,
            "comparison_id": comparison_id,
            "decision_id": decision_id,
            "observation_id": observation_id,
            "execution_id": execution_id,
            "algorithm_version": algorithm_version,
        }
    )


generate_outcome_evaluation_id = derive_outcome_evaluation_id
generate_forecast_comparison_outcome_evidence_id = (
    derive_forecast_comparison_outcome_evidence_id
)


def _required_identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid_{field}")
    return value


def _digest_identifier(value: object, *, field: str) -> str:
    identity = _required_identifier(value, field=field)
    if len(identity) != 64 or any(
        character not in "0123456789abcdef" for character in identity
    ):
        raise ValueError(f"invalid_{field}")
    return identity


def _utc(value: object, *, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"invalid_{field}")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ForecastComparisonOutcomeEvidence:
    evidence_id: str
    comparison_id: str
    decision_id: str
    observation_id: str
    execution_id: str
    algorithm_version: str
    derived_at_utc: datetime
    source_type: ForecastComparisonOutcomeEvidenceSourceType = (
        ForecastComparisonOutcomeEvidenceSourceType.SYSTEM_DERIVED
    )

    def __post_init__(self) -> None:
        _digest_identifier(self.evidence_id, field="evidence_id")
        _digest_identifier(self.comparison_id, field="comparison_id")
        for field in ("decision_id", "observation_id", "execution_id"):
            _required_identifier(getattr(self, field), field=field)
        _required_identifier(self.algorithm_version, field="algorithm_version")
        if (
            self.source_type
            is not ForecastComparisonOutcomeEvidenceSourceType.SYSTEM_DERIVED
        ):
            raise ValueError("invalid_outcome_evidence_source_type")
        object.__setattr__(
            self,
            "derived_at_utc",
            _utc(self.derived_at_utc, field="derived_at_utc"),
        )


@dataclass(frozen=True, slots=True)
class OutcomeEvaluation:
    evaluation_id: str
    comparison: ForecastObservationComparison
    outcome_evidence: ForecastComparisonOutcomeEvidence | None = None
    assessment: OutcomeAssessment | None = None
    evaluation_algorithm_version: str = OUTCOME_EVALUATION_ALGORITHM_VERSION

    def __post_init__(self) -> None:
        _digest_identifier(self.evaluation_id, field="evaluation_id")
        _required_identifier(
            self.evaluation_algorithm_version,
            field="evaluation_algorithm_version",
        )
        if type(self.comparison) is not ForecastObservationComparison:
            raise ValueError("invalid_forecast_observation_comparison")
        if not self.comparison.identity_persistable:
            raise ValueError("comparison_identity_not_persistable")
        expected_evaluation_id = derive_outcome_evaluation_id(
            comparison_id=self.comparison.comparison_id,
            evaluation_algorithm_version=self.evaluation_algorithm_version,
        )
        if self.evaluation_id != expected_evaluation_id:
            raise ValueError("evaluation_id_mismatch")

        execution_id = self.comparison.execution_id
        if execution_id is None:
            if self.outcome_evidence is not None or self.assessment is not None:
                raise ValueError("decision_only_evaluation_has_execution_artifacts")
            return
        if self.outcome_evidence is None or self.assessment is None:
            raise ValueError("execution_evaluation_requires_evidence_and_assessment")
        if type(self.outcome_evidence) is not ForecastComparisonOutcomeEvidence:
            raise ValueError("invalid_forecast_comparison_outcome_evidence")
        if type(self.assessment) is not OutcomeAssessment:
            raise ValueError("invalid_outcome_assessment")
        evidence = self.outcome_evidence
        if self.comparison.decision_id is None:
            raise ValueError("execution_comparison_requires_decision_id")
        if evidence.comparison_id != self.comparison.comparison_id:
            raise ValueError("evidence_comparison_id_mismatch")
        if evidence.decision_id != self.comparison.decision_id:
            raise ValueError("evidence_decision_id_mismatch")
        if evidence.observation_id != self.comparison.observation_id:
            raise ValueError("evidence_observation_id_mismatch")
        if evidence.execution_id != execution_id:
            raise ValueError("evidence_execution_id_mismatch")
        expected_evidence_id = derive_forecast_comparison_outcome_evidence_id(
            evaluation_id=self.evaluation_id,
            comparison_id=evidence.comparison_id,
            decision_id=evidence.decision_id,
            observation_id=evidence.observation_id,
            execution_id=evidence.execution_id,
            algorithm_version=evidence.algorithm_version,
        )
        if evidence.evidence_id != expected_evidence_id:
            raise ValueError("evidence_id_mismatch")
        if self.assessment.execution_id != execution_id:
            raise ValueError("assessment_execution_id_mismatch")
        if self.assessment.evidence_ids != (evidence.evidence_id,):
            raise ValueError("assessment_evidence_ids_mismatch")
        if any(
            finding.evidence_ids != (evidence.evidence_id,)
            for finding in self.assessment.findings
        ):
            raise ValueError("assessment_finding_evidence_ids_mismatch")
