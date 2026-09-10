from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timedelta, timezone
import inspect

import pytest

from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    FieldOutcomeEvidence,
    ImageOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)
from decision.models.portfolio_credit import PortfolioCredit
from decision.services import portfolio_credit_validation
from decision.services.portfolio_credit_validation import validate_portfolio_credit


RECORDED_AT = datetime(2026, 9, 10, 23, tzinfo=timezone.utc)
STARTED_AT = datetime(2026, 9, 10, 21, tzinfo=timezone.utc)
ENDED_AT = datetime(2026, 9, 10, 23, tzinfo=timezone.utc)


def execution(status=ExecutionStatus.COMPLETED, execution_id="execution-1"):
    if status in (ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED):
        return Execution(
            execution_id, "mission-1", status, STARTED_AT, ENDED_AT, timedelta(hours=2)
        )
    if status is ExecutionStatus.IN_PROGRESS:
        return Execution(execution_id, "mission-1", status, STARTED_AT, None, None)
    return Execution(execution_id, "mission-1", status, None, None, None)


def acquisition(
    evidence_id="evidence-1",
    execution_id="execution-1",
    usable=timedelta(minutes=40),
    capture=timedelta(minutes=60),
):
    return AcquisitionOutcomeEvidence(
        evidence_id=evidence_id,
        execution_id=execution_id,
        category=OutcomeEvidenceCategory.ACQUISITION,
        observed_at=RECORDED_AT,
        source=OutcomeEvidenceSource.USER,
        actual_capture_duration=capture,
        usable_integration_duration=usable,
    )


def credit(**changes):
    values = {
        "credit_id": "credit-1",
        "execution_id": "execution-1",
        "evidence_ids": ("evidence-1",),
        "usable_integration_duration": timedelta(minutes=40),
        "credited_at": RECORDED_AT,
    }
    values.update(changes)
    return PortfolioCredit(**values)


@pytest.mark.parametrize("status", [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED])
def test_valid_closed_execution_credit(status):
    record = credit()
    assert validate_portfolio_credit(record, execution(status), (acquisition(),)) is record


def test_explicit_zero_usable_integration_accepted():
    record = credit(usable_integration_duration=timedelta(0))
    assert validate_portfolio_credit(
        record, execution(), (acquisition(usable=timedelta(0)),)
    ) is record


@pytest.mark.parametrize("status", [
    ExecutionStatus.NOT_STARTED,
    ExecutionStatus.IN_PROGRESS,
    ExecutionStatus.UNCONFIRMED,
])
def test_ineligible_execution_status_rejected_even_with_acquisition_evidence(status):
    source_execution = execution(status)
    before = asdict(source_execution)
    with pytest.raises(ValueError, match="execution_status_ineligible"):
        validate_portfolio_credit(credit(), source_execution, (acquisition(),))
    assert asdict(source_execution) == before
    assert source_execution.status is status


def test_actual_capture_duration_alone_cannot_produce_credit():
    with pytest.raises(ValueError, match="explicit_usable_integration_required"):
        validate_portfolio_credit(
            credit(), execution(), (acquisition(usable=None, capture=timedelta(hours=2)),)
        )


def test_execution_actual_duration_alone_cannot_produce_credit():
    with pytest.raises(ValueError, match="explicit_usable_integration_required"):
        validate_portfolio_credit(
            credit(usable_integration_duration=timedelta(hours=2)),
            execution(),
            (acquisition(usable=None, capture=None),),
        )


def test_usable_integration_not_derived_from_capture_or_execution_duration():
    record = credit(usable_integration_duration=timedelta(minutes=15))
    assert validate_portfolio_credit(
        record,
        execution(),
        (acquisition(usable=timedelta(minutes=15), capture=timedelta(minutes=90)),),
    ) is record
    assert record.usable_integration_duration != timedelta(minutes=90)
    assert record.usable_integration_duration != execution().actual_duration


@pytest.mark.parametrize("name", ["credit_id", "execution_id"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 1, True, (), {}])
def test_invalid_identifiers_rejected(name, value):
    with pytest.raises((TypeError, ValueError)):
        credit(**{name: value})


@pytest.mark.parametrize("value", [
    datetime(2026, 9, 10, 23), None, "2026-09-10T23:00:00Z", 0
])
def test_invalid_or_naive_credited_at_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        credit(credited_at=value)


@pytest.mark.parametrize("value", [timedelta(microseconds=-1), -1, 0, True, "40", None, {}])
def test_negative_or_untyped_credit_duration_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        credit(usable_integration_duration=value)


@pytest.mark.parametrize("evidence_ids", [
    (),
    ("evidence-1", "evidence-1"),
    ("evidence-1", ""),
    ("evidence-1", "  "),
    ("evidence-1", 1),
    ["evidence-1"],
    "evidence-1",
    None,
])
def test_empty_duplicate_or_malformed_evidence_ids_rejected(evidence_ids):
    with pytest.raises((TypeError, ValueError)):
        credit(evidence_ids=evidence_ids)


def test_cross_execution_evidence_rejected():
    with pytest.raises(ValueError, match="evidence_execution_mismatch"):
        validate_portfolio_credit(
            credit(), execution(), (acquisition(execution_id="execution-2"),)
        )


def test_credit_execution_identity_must_match_execution():
    with pytest.raises(ValueError, match="credit_execution_mismatch"):
        validate_portfolio_credit(credit(execution_id="execution-2"), execution(), (acquisition(),))


@pytest.mark.parametrize("kind,category", [
    (FieldOutcomeEvidence, OutcomeEvidenceCategory.FIELD),
    (TechnicalOutcomeEvidence, OutcomeEvidenceCategory.TECHNICAL),
    (ImageOutcomeEvidence, OutcomeEvidenceCategory.IMAGE),
])
def test_non_acquisition_evidence_cannot_contribute_duration(kind, category):
    item = kind(
        evidence_id="evidence-1",
        execution_id="execution-1",
        category=category,
        observed_at=RECORDED_AT,
        source=OutcomeEvidenceSource.USER,
    )
    with pytest.raises(ValueError, match="acquisition_evidence_required"):
        validate_portfolio_credit(credit(), execution(), (item,))


def test_multiple_acquisition_records_sum_only_explicit_usable_integration():
    record = credit(
        evidence_ids=("evidence-1", "evidence-2"),
        usable_integration_duration=timedelta(minutes=55),
    )
    evidence_records = (
        acquisition("evidence-1", usable=timedelta(minutes=20), capture=timedelta(minutes=80)),
        acquisition("evidence-2", usable=timedelta(minutes=35), capture=timedelta(minutes=90)),
    )
    assert validate_portfolio_credit(record, execution(), evidence_records) is record


def test_explicit_credit_total_mismatch_rejected():
    with pytest.raises(ValueError, match="usable_integration_total_mismatch"):
        validate_portfolio_credit(
            credit(usable_integration_duration=timedelta(minutes=39)),
            execution(),
            (acquisition(usable=timedelta(minutes=40)),),
        )


def test_missing_unrelated_and_duplicate_evidence_records_rejected():
    record = credit()
    with pytest.raises(ValueError, match="evidence_records_mismatch"):
        validate_portfolio_credit(record, execution(), ())
    with pytest.raises(ValueError, match="evidence_records_mismatch"):
        validate_portfolio_credit(
            record, execution(), (acquisition(), acquisition("evidence-2"))
        )
    item = acquisition()
    with pytest.raises(ValueError, match="duplicate_evidence_record"):
        validate_portfolio_credit(record, execution(), (item, item))


def test_source_execution_and_evidence_remain_unmodified():
    source_execution = execution(ExecutionStatus.INTERRUPTED)
    source_evidence = acquisition()
    execution_before = asdict(source_execution)
    evidence_before = asdict(source_evidence)
    validate_portfolio_credit(credit(), source_execution, (source_evidence,))
    assert asdict(source_execution) == execution_before
    assert asdict(source_evidence) == evidence_before


def test_portfolio_credit_is_immutable():
    record = credit()
    for field in fields(record):
        with pytest.raises(FrozenInstanceError):
            setattr(record, field.name, getattr(record, field.name))


@pytest.mark.parametrize("missing", [
    "credit_id", "execution_id", "evidence_ids", "usable_integration_duration", "credited_at"
])
def test_no_hidden_provenance_or_duration_defaults(missing):
    values = {
        "credit_id": "credit-1",
        "execution_id": "execution-1",
        "evidence_ids": ("evidence-1",),
        "usable_integration_duration": timedelta(minutes=40),
        "credited_at": RECORDED_AT,
    }
    del values[missing]
    with pytest.raises(TypeError):
        PortfolioCredit(**values)


def test_contract_has_no_assessment_mutation_or_learning_behavior():
    assert {field.name for field in fields(PortfolioCredit)} == {
        "credit_id", "execution_id", "evidence_ids", "usable_integration_duration", "credited_at"
    }
    forbidden = {
        "outcome_assessment", "assessment_id", "portfolio", "project", "learning",
        "score", "quality", "actual_capture_duration", "execution",
    }
    assert forbidden.isdisjoint(field.name for field in fields(PortfolioCredit))
    assert "OutcomeAssessment" not in inspect.getsource(portfolio_credit_validation)
