"""Pure validation of an assessment against explicitly supplied evidence."""

from decision.models.outcome_assessment import OutcomeAssessment
from decision.models.outcome_evidence import OutcomeEvidence


def validate_outcome_assessment(
    assessment: OutcomeAssessment,
    evidence_records: tuple[OutcomeEvidence, ...],
) -> OutcomeAssessment:
    """Return the unchanged assessment after strict provenance validation."""

    if type(assessment) is not OutcomeAssessment:
        raise TypeError("assessment_must_be_outcome_assessment")
    if not isinstance(evidence_records, tuple):
        raise TypeError("evidence_records_must_be_tuple")
    if not all(isinstance(record, OutcomeEvidence) for record in evidence_records):
        raise TypeError("evidence_records_must_contain_outcome_evidence")

    supplied_ids = tuple(record.evidence_id for record in evidence_records)
    if len(set(supplied_ids)) != len(supplied_ids):
        raise ValueError("duplicate_evidence_record")
    if set(supplied_ids) != set(assessment.evidence_ids):
        raise ValueError("evidence_records_mismatch")
    if any(record.execution_id != assessment.execution_id for record in evidence_records):
        raise ValueError("evidence_execution_mismatch")
    return assessment
