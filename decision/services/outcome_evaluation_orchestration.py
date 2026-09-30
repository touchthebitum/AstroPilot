from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from decision.field_observation import FieldObservation
from decision.field_observation_persistence import (
    FieldObservationPersistenceError,
    FieldObservationStore,
)
from decision.models.forecast_observation_comparison import (
    ForecastObservationComparison,
    ForecastObservationComparisonStatus,
    ForecastObservationParameters,
    VariableComparisonStatus,
)
from decision.models.outcome_assessment import (
    OutcomeAssessment,
    OutcomeAssessmentStatus,
    OutcomeFinding,
)
from decision.models.outcome_evaluation import (
    FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION,
    OUTCOME_EVALUATION_ALGORITHM_VERSION,
    ForecastComparisonOutcomeEvidence,
    ForecastComparisonOutcomeEvidenceSourceType,
    OutcomeEvaluation,
    derive_forecast_comparison_outcome_evidence_id,
    derive_outcome_evaluation_id,
)
from decision.outcome_evaluation_persistence import OutcomeEvaluationStore
from decision.services.field_observation_context import (
    FieldObservationContextResolver,
)
from decision.services.forecast_observation_comparison import (
    compare_forecast_to_field_observation,
)
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidenceStore,
)


OUTCOME_ASSESSMENT_POLICY_VERSION = "outcome_assessment.v1"


class OutcomeEvaluationOrchestrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OutcomeEvaluationOrchestrationResult:
    evaluation: OutcomeEvaluation
    created: bool


def _digest(fields: dict[str, str]) -> str:
    encoded = json.dumps(
        fields,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assessment_status(
    comparison: ForecastObservationComparison,
) -> OutcomeAssessmentStatus:
    if comparison.status is ForecastObservationComparisonStatus.NOT_COMPARABLE:
        return OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE
    if comparison.status is ForecastObservationComparisonStatus.PARTIAL:
        return OutcomeAssessmentStatus.PARTIAL
    if comparison.status is ForecastObservationComparisonStatus.COMPARABLE:
        return OutcomeAssessmentStatus.SUFFICIENT
    raise OutcomeEvaluationOrchestrationError("unsupported_comparison_status")


def _build_assessment(
    *,
    comparison: ForecastObservationComparison,
    evaluation_id: str,
    evidence_id: str,
    assessed_at: datetime,
) -> OutcomeAssessment:
    if comparison.execution_id is None:
        raise OutcomeEvaluationOrchestrationError(
            "assessment_requires_execution"
        )
    status = _assessment_status(comparison)
    comparable_results = tuple(
        result
        for result in comparison.results
        if result.status is VariableComparisonStatus.COMPARABLE
    )
    if (
        status is OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE
        and comparable_results
    ):
        raise OutcomeEvaluationOrchestrationError(
            "invalid_not_comparable_result"
        )

    findings = tuple(
        OutcomeFinding(
            finding_id=_digest(
                {
                    "artifact_type": "OutcomeFinding",
                    "evaluation_id": evaluation_id,
                    "evidence_id": evidence_id,
                    "basis": (
                        f"forecast_observation.{result.variable.value}.comparable"
                    ),
                    "policy_version": OUTCOME_ASSESSMENT_POLICY_VERSION,
                }
            ),
            basis=f"forecast_observation.{result.variable.value}.comparable",
            evidence_ids=(evidence_id,),
        )
        for result in comparable_results
    )
    return OutcomeAssessment(
        assessment_id=_digest(
            {
                "artifact_type": "OutcomeAssessment",
                "evaluation_id": evaluation_id,
                "evidence_id": evidence_id,
                "status": status.value,
                "policy_version": OUTCOME_ASSESSMENT_POLICY_VERSION,
            }
        ),
        execution_id=comparison.execution_id,
        evidence_ids=(evidence_id,),
        assessed_at=assessed_at,
        status=status,
        findings=findings,
    )


class OutcomeEvaluationOrchestrationService:
    def __init__(
        self,
        *,
        observation_store: FieldObservationStore,
        forecast_evidence_store: DecisionForecastEvidenceStore,
        outcome_evaluation_store: OutcomeEvaluationStore,
        context_resolver: FieldObservationContextResolver,
        clock: Callable[[], datetime],
        comparison_parameters: ForecastObservationParameters | None = None,
    ) -> None:
        self.observation_store = observation_store
        self.forecast_evidence_store = forecast_evidence_store
        self.outcome_evaluation_store = outcome_evaluation_store
        self.context_resolver = context_resolver
        self.clock = clock
        self.comparison_parameters = (
            ForecastObservationParameters()
            if comparison_parameters is None
            else comparison_parameters
        )

    @staticmethod
    def _utc_instant(value: object) -> datetime:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise OutcomeEvaluationOrchestrationError("invalid_clock")
        return value.astimezone(timezone.utc)

    def _initial_observation(self, observation_id: str) -> FieldObservation:
        observation = self.observation_store.load(
            observation_id=observation_id
        )
        if observation is None:
            raise FieldObservationPersistenceError(
                "field_observation_missing"
            )
        return observation

    def _comparison(
        self,
        *,
        observation: FieldObservation,
        evidence: object,
        computed_at: datetime,
    ) -> ForecastObservationComparison:
        comparison = compare_forecast_to_field_observation(
            evidence,
            observation,
            computed_at_utc=computed_at,
            parameters=self.comparison_parameters,
        )
        if not comparison.identity_persistable:
            raise OutcomeEvaluationOrchestrationError(
                "comparison_identity_not_persistable"
            )
        return comparison

    @staticmethod
    def _evaluation(
        *,
        comparison: ForecastObservationComparison,
        artifact_time: datetime,
    ) -> OutcomeEvaluation:
        evaluation_id = derive_outcome_evaluation_id(
            comparison_id=comparison.comparison_id,
            evaluation_algorithm_version=OUTCOME_EVALUATION_ALGORITHM_VERSION,
        )
        if comparison.execution_id is None:
            return OutcomeEvaluation(
                evaluation_id=evaluation_id,
                comparison=comparison,
            )
        if comparison.decision_id is None:
            raise OutcomeEvaluationOrchestrationError(
                "execution_comparison_requires_decision_id"
            )
        evidence_id = derive_forecast_comparison_outcome_evidence_id(
            evaluation_id=evaluation_id,
            comparison_id=comparison.comparison_id,
            decision_id=comparison.decision_id,
            observation_id=comparison.observation_id,
            execution_id=comparison.execution_id,
            algorithm_version=(
                FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION
            ),
        )
        outcome_evidence = ForecastComparisonOutcomeEvidence(
            evidence_id=evidence_id,
            comparison_id=comparison.comparison_id,
            decision_id=comparison.decision_id,
            observation_id=comparison.observation_id,
            execution_id=comparison.execution_id,
            algorithm_version=(
                FORECAST_COMPARISON_OUTCOME_EVIDENCE_ALGORITHM_VERSION
            ),
            derived_at_utc=artifact_time,
            source_type=(
                ForecastComparisonOutcomeEvidenceSourceType.SYSTEM_DERIVED
            ),
        )
        return OutcomeEvaluation(
            evaluation_id=evaluation_id,
            comparison=comparison,
            outcome_evidence=outcome_evidence,
            assessment=_build_assessment(
                comparison=comparison,
                evaluation_id=evaluation_id,
                evidence_id=evidence_id,
                assessed_at=artifact_time,
            ),
        )

    def evaluate(
        self,
        observation_id: str,
    ) -> OutcomeEvaluationOrchestrationResult:
        # Resolve lineage before the nested persistence critical section. The
        # active lease below re-reads the canonical observation under lock.
        initial_observation = self._initial_observation(observation_id)
        self.context_resolver.resolve(initial_observation)

        with self.observation_store.active_observation_lease(
            observation_id=observation_id
        ) as observation:
            evidence = self.forecast_evidence_store.load(
                decision_id=observation.decision_id
            )
            if evidence is None:
                raise OutcomeEvaluationOrchestrationError(
                    "decision_forecast_evidence_missing"
                )

            artifact_time = self._utc_instant(self.clock())
            comparison = self._comparison(
                observation=observation,
                evidence=evidence,
                computed_at=artifact_time,
            )
            evaluation_id = derive_outcome_evaluation_id(
                comparison_id=comparison.comparison_id,
                evaluation_algorithm_version=(
                    OUTCOME_EVALUATION_ALGORITHM_VERSION
                ),
            )
            existing_for_observation = (
                self.outcome_evaluation_store.list_by_observation(
                    observation_id=observation.observation_id
                )
            )
            existing = None
            for candidate in existing_for_observation:
                if (
                    candidate.evaluation_algorithm_version
                    == OUTCOME_EVALUATION_ALGORITHM_VERSION
                ):
                    if candidate.evaluation_id != evaluation_id:
                        raise OutcomeEvaluationOrchestrationError(
                            "outcome_evaluation_conflict"
                        )
                    existing = candidate
            if existing is not None:
                artifact_time = existing.comparison.computed_at_utc
                comparison = self._comparison(
                    observation=observation,
                    evidence=evidence,
                    computed_at=artifact_time,
                )

            evaluation = self._evaluation(
                comparison=comparison,
                artifact_time=artifact_time,
            )
            created = self.outcome_evaluation_store.save(
                evaluation=evaluation
            )
            return OutcomeEvaluationOrchestrationResult(
                evaluation=evaluation,
                created=created,
            )
