"""Pure provenance validation for a candidate LearningSignal."""

from decision.models.learning_eligibility import (
    LearningEligibility,
    LearningEligibilityReasonCode,
    LearningEligibilityStatus,
)
from decision.models.learning_signal import LearningSignal
from decision.models.outcome_assessment import OutcomeAssessment
from decision.models.outcome_evidence import OutcomeEvidence


def validate_learning_signal(
    signal: LearningSignal,
    eligibility: LearningEligibility,
    assessment: OutcomeAssessment,
    evidence_records: tuple[OutcomeEvidence, ...],
) -> LearningSignal:
    """Return the unchanged signal after validating its existing provenance path."""

    if type(signal) is not LearningSignal:
        raise TypeError("signal_must_be_learning_signal")
    if type(eligibility) is not LearningEligibility:
        raise TypeError("eligibility_must_be_learning_eligibility")
    if type(assessment) is not OutcomeAssessment:
        raise TypeError("assessment_must_be_outcome_assessment")
    if not isinstance(evidence_records, tuple):
        raise TypeError("evidence_records_must_be_tuple")
    if not all(isinstance(record, OutcomeEvidence) for record in evidence_records):
        raise TypeError("evidence_records_must_contain_outcome_evidence")
    if eligibility.status is not LearningEligibilityStatus.ELIGIBLE:
        raise ValueError("eligible_learning_eligibility_required")
    if signal.eligibility != eligibility:
        raise ValueError("eligibility_provenance_mismatch")
    if signal.execution_id != eligibility.execution_id:
        raise ValueError("eligibility_execution_mismatch")
    if signal.assessment_id != eligibility.assessment_id:
        raise ValueError("eligibility_assessment_mismatch")
    if assessment.execution_id != signal.execution_id:
        raise ValueError("assessment_execution_mismatch")
    if assessment.assessment_id != signal.assessment_id:
        raise ValueError("assessment_id_mismatch")

    matching_reasons = tuple(
        reason
        for reason in eligibility.reasons
        if reason.code is LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING
        and reason.dimension is signal.dimension
        and reason.evidence_ids == signal.evidence_ids
    )
    if len(matching_reasons) != 1:
        raise ValueError("eligibility_reason_provenance_ambiguous")
    eligibility_reason = matching_reasons[0]
    matching_findings = tuple(
        finding
        for finding in assessment.findings
        if finding.finding_id == eligibility_reason.finding_id
        and finding.basis == signal.dimension.value
        and finding.evidence_ids == signal.evidence_ids
    )
    if len(matching_findings) != 1:
        raise ValueError("eligibility_finding_provenance_mismatch")
    if not set(signal.evidence_ids).issubset(assessment.evidence_ids):
        raise ValueError("evidence_not_supported_by_assessment")

    supplied_ids = tuple(record.evidence_id for record in evidence_records)
    if len(set(supplied_ids)) != len(supplied_ids):
        raise ValueError("duplicate_evidence_record")
    if set(supplied_ids) != set(signal.evidence_ids):
        raise ValueError("evidence_records_mismatch")
    if any(record.execution_id != signal.execution_id for record in evidence_records):
        raise ValueError("evidence_execution_mismatch")
    return signal
