"""Pure evaluator for reliable learning-signal eligibility."""

from decision.models.execution import Execution, ExecutionStatus
from decision.models.learning_eligibility import (
    LearnableDimension,
    LearningEligibility,
    LearningEligibilityReason,
    LearningEligibilityReasonCode,
    LearningEligibilityStatus,
)
from decision.models.outcome_assessment import OutcomeAssessment, OutcomeAssessmentStatus
from decision.models.outcome_evidence import OutcomeEvidence, TechnicalOutcomeEvidence
from decision.services.outcome_assessment_validation import validate_outcome_assessment


_EXECUTION_REASON_CODES = {
    ExecutionStatus.NOT_STARTED: LearningEligibilityReasonCode.EXECUTION_NOT_STARTED,
    ExecutionStatus.IN_PROGRESS: LearningEligibilityReasonCode.EXECUTION_IN_PROGRESS,
    ExecutionStatus.UNCONFIRMED: LearningEligibilityReasonCode.EXECUTION_UNCONFIRMED,
}


def evaluate_learning_eligibility(
    execution: Execution,
    assessment: OutcomeAssessment | None = None,
    evidence_records: tuple[OutcomeEvidence, ...] = (),
) -> LearningEligibility:
    """Evaluate explicit provenance without performing or persisting Learning."""

    if type(execution) is not Execution:
        raise TypeError("execution_must_be_execution")
    if assessment is not None and type(assessment) is not OutcomeAssessment:
        raise TypeError("assessment_must_be_outcome_assessment")
    if not isinstance(evidence_records, tuple):
        raise TypeError("evidence_records_must_be_tuple")
    if assessment is None and evidence_records:
        raise ValueError("assessment_required_for_evidence")
    if assessment is not None:
        if assessment.execution_id != execution.execution_id:
            raise ValueError("assessment_execution_mismatch")
        validate_outcome_assessment(assessment, evidence_records)

    execution_reason = _EXECUTION_REASON_CODES.get(execution.status)
    if execution_reason is not None:
        return LearningEligibility(
            execution_id=execution.execution_id,
            assessment_id=None,
            status=LearningEligibilityStatus.NOT_ELIGIBLE,
            reasons=(LearningEligibilityReason(execution_reason),),
        )
    if assessment is None:
        raise ValueError("assessment_required")
    if assessment.status is OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE:
        return LearningEligibility(
            execution_id=execution.execution_id,
            assessment_id=assessment.assessment_id,
            status=LearningEligibilityStatus.INSUFFICIENT_EVIDENCE,
            reasons=(LearningEligibilityReason(
                LearningEligibilityReasonCode.ASSESSMENT_INSUFFICIENT_EVIDENCE
            ),),
        )

    evidence_by_id = {record.evidence_id: record for record in evidence_records}
    supported_reasons = tuple(
        LearningEligibilityReason(
            code=LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING,
            dimension=LearnableDimension.TECHNICAL,
            finding_id=finding.finding_id,
            evidence_ids=finding.evidence_ids,
        )
        for finding in assessment.findings
        if finding.basis == LearnableDimension.TECHNICAL.value
        and all(
            type(evidence_by_id[evidence_id]) is TechnicalOutcomeEvidence
            for evidence_id in finding.evidence_ids
        )
    )
    if supported_reasons:
        return LearningEligibility(
            execution_id=execution.execution_id,
            assessment_id=assessment.assessment_id,
            status=LearningEligibilityStatus.ELIGIBLE,
            reasons=supported_reasons,
        )
    return LearningEligibility(
        execution_id=execution.execution_id,
        assessment_id=assessment.assessment_id,
        status=LearningEligibilityStatus.NOT_ELIGIBLE,
        reasons=(LearningEligibilityReason(
            LearningEligibilityReasonCode.NO_SUPPORTED_LEARNABLE_FINDING
        ),),
    )
