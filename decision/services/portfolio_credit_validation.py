"""Pure validation of explicit portfolio credit provenance and duration."""

from datetime import timedelta

from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import AcquisitionOutcomeEvidence, OutcomeEvidence
from decision.models.portfolio_credit import PortfolioCredit


def validate_portfolio_credit(
    credit: PortfolioCredit,
    execution: Execution,
    evidence_records: tuple[OutcomeEvidence, ...],
) -> PortfolioCredit:
    """Return unchanged credit after validating explicit eligible evidence."""

    if type(credit) is not PortfolioCredit:
        raise TypeError("credit_must_be_portfolio_credit")
    if type(execution) is not Execution:
        raise TypeError("execution_must_be_execution")
    if not isinstance(evidence_records, tuple):
        raise TypeError("evidence_records_must_be_tuple")
    if not all(isinstance(record, OutcomeEvidence) for record in evidence_records):
        raise TypeError("evidence_records_must_contain_outcome_evidence")
    if credit.execution_id != execution.execution_id:
        raise ValueError("credit_execution_mismatch")
    if execution.status not in (ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED):
        raise ValueError("execution_status_ineligible")

    supplied_ids = tuple(record.evidence_id for record in evidence_records)
    if len(set(supplied_ids)) != len(supplied_ids):
        raise ValueError("duplicate_evidence_record")
    if set(supplied_ids) != set(credit.evidence_ids):
        raise ValueError("evidence_records_mismatch")
    if any(record.execution_id != credit.execution_id for record in evidence_records):
        raise ValueError("evidence_execution_mismatch")
    if any(type(record) is not AcquisitionOutcomeEvidence for record in evidence_records):
        raise ValueError("acquisition_evidence_required")
    if any(record.usable_integration_duration is None for record in evidence_records):
        raise ValueError("explicit_usable_integration_required")

    evidenced_total = sum(
        (record.usable_integration_duration for record in evidence_records),
        start=timedelta(0),
    )
    if credit.usable_integration_duration != evidenced_total:
        raise ValueError("usable_integration_total_mismatch")
    return credit
