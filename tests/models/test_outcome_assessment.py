from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timezone

import pytest

from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_assessment import (
    OutcomeAssessment,
    OutcomeAssessmentStatus,
    OutcomeFinding,
)
from decision.models.outcome_evidence import (
    FieldOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)
from decision.services.outcome_assessment_validation import validate_outcome_assessment


ASSESSED_AT = datetime(2026, 9, 10, 23, tzinfo=timezone.utc)
OBSERVED_AT = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)


def evidence(evidence_id="evidence-1", execution_id="execution-1"):
    return FieldOutcomeEvidence(
        evidence_id=evidence_id,
        execution_id=execution_id,
        category=OutcomeEvidenceCategory.FIELD,
        observed_at=OBSERVED_AT,
        source=OutcomeEvidenceSource.USER,
    )


def finding(evidence_ids=("evidence-1",)):
    return OutcomeFinding(
        finding_id="finding-1",
        basis="field_observation_recorded",
        evidence_ids=evidence_ids,
    )


def assessment(status=OutcomeAssessmentStatus.SUFFICIENT, **changes):
    values = {
        "assessment_id": "assessment-1",
        "execution_id": "execution-1",
        "evidence_ids": ("evidence-1",),
        "assessed_at": ASSESSED_AT,
        "status": status,
        "findings": (finding(),),
    }
    values.update(changes)
    return OutcomeAssessment(**values)


@pytest.mark.parametrize("status", list(OutcomeAssessmentStatus))
def test_valid_assessment_statuses(status):
    findings = () if status is OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE else (finding(),)
    record = assessment(status, findings=findings)
    assert validate_outcome_assessment(record, (evidence(),)) is record


def test_status_contract_has_no_overall_verdict():
    assert {member.name for member in OutcomeAssessmentStatus} == {
        "SUFFICIENT", "PARTIAL", "INSUFFICIENT_EVIDENCE"
    }
    forbidden = {"SUCCESS", "FAILURE", "GOOD", "BAD", "PASS", "FAIL"}
    assert forbidden.isdisjoint(OutcomeAssessmentStatus.__members__)
    assert "failure" not in OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE.value
    assert "poor" not in OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE.value


@pytest.mark.parametrize("name", ["assessment_id", "execution_id"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 1, True, (), {}])
def test_invalid_identifiers_rejected(name, value):
    with pytest.raises((TypeError, ValueError)):
        assessment(**{name: value})


@pytest.mark.parametrize("value", [datetime(2026, 9, 10, 23), None, "2026-09-10T23:00:00Z", 0])
def test_invalid_or_naive_assessed_at_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        assessment(assessed_at=value)


def test_zero_referenced_evidence_rejected():
    with pytest.raises(ValueError, match="evidence_required"):
        assessment(evidence_ids=(), findings=())


@pytest.mark.parametrize("evidence_ids", [
    ("evidence-1", "evidence-1"),
    ("evidence-1", ""),
    ("evidence-1", "  "),
    ("evidence-1", 1),
    ["evidence-1"],
    "evidence-1",
    None,
])
def test_malformed_or_duplicate_assessment_evidence_ids_rejected(evidence_ids):
    with pytest.raises((TypeError, ValueError)):
        assessment(evidence_ids=evidence_ids)


def test_evidence_from_another_execution_rejected():
    with pytest.raises(ValueError, match="execution_mismatch"):
        validate_outcome_assessment(assessment(), (evidence(execution_id="execution-2"),))


def test_missing_and_unrelated_evidence_records_rejected():
    with pytest.raises(ValueError, match="evidence_records_mismatch"):
        validate_outcome_assessment(assessment(), ())
    with pytest.raises(ValueError, match="evidence_records_mismatch"):
        validate_outcome_assessment(
            assessment(), (evidence(), evidence("evidence-2"))
        )


def test_duplicate_evidence_records_rejected():
    item = evidence()
    with pytest.raises(ValueError, match="duplicate_evidence_record"):
        validate_outcome_assessment(assessment(), (item, item))


def test_finding_with_dangling_evidence_reference_rejected():
    with pytest.raises(ValueError, match="finding_evidence_not_in_assessment"):
        assessment(findings=(finding(("evidence-2",)),))


def test_finding_supported_by_subset_of_assessment_evidence_accepted():
    second = TechnicalOutcomeEvidence(
        evidence_id="evidence-2",
        execution_id="execution-1",
        category=OutcomeEvidenceCategory.TECHNICAL,
        observed_at=OBSERVED_AT,
        source=OutcomeEvidenceSource.USER,
    )
    record = assessment(evidence_ids=("evidence-1", "evidence-2"))
    assert validate_outcome_assessment(record, (evidence(), second)) is record


@pytest.mark.parametrize("evidence_ids", [(), ("evidence-1", "evidence-1")])
def test_finding_requires_unambiguous_support(evidence_ids):
    with pytest.raises(ValueError):
        OutcomeFinding("finding-1", "basis", evidence_ids)


@pytest.mark.parametrize("name", ["finding_id", "basis"])
@pytest.mark.parametrize("value", ["", "  ", None, 1, True, (), {}])
def test_malformed_finding_identity_or_basis_rejected(name, value):
    values = {"finding_id": "finding-1", "basis": "basis", "evidence_ids": ("evidence-1",)}
    values[name] = value
    with pytest.raises((TypeError, ValueError)):
        OutcomeFinding(**values)


@pytest.mark.parametrize("value", [[finding()], {"finding": finding()}, "finding", None, (object(),)])
def test_malformed_findings_structure_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        assessment(findings=value)


@pytest.mark.parametrize("value", ["sufficient", "success", None, 1, {}])
def test_unsupported_or_untyped_status_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        assessment(status=value)


def test_source_evidence_remains_unmodified():
    item = evidence()
    before = asdict(item)
    validate_outcome_assessment(assessment(), (item,))
    assert asdict(item) == before
    with pytest.raises(FrozenInstanceError):
        item.execution_id = "changed"


def test_assessment_and_finding_are_immutable():
    record = assessment()
    for item in (record, record.findings[0]):
        for field in fields(item):
            with pytest.raises(FrozenInstanceError):
                setattr(item, field.name, getattr(item, field.name))


@pytest.mark.parametrize("kind,values", [
    (OutcomeFinding, {"basis": "basis", "evidence_ids": ("evidence-1",)}),
    (OutcomeAssessment, {
        "assessment_id": "assessment-1", "execution_id": "execution-1",
        "evidence_ids": ("evidence-1",), "status": OutcomeAssessmentStatus.SUFFICIENT,
        "findings": (finding(),),
    }),
])
def test_no_hidden_timestamp_or_provenance_defaults(kind, values):
    with pytest.raises(TypeError):
        kind(**values)


def test_contract_has_no_score_credit_learning_or_mutation_fields():
    assert {field.name for field in fields(OutcomeAssessment)} == {
        "assessment_id", "execution_id", "evidence_ids", "assessed_at", "status", "findings"
    }
    assert {field.name for field in fields(OutcomeFinding)} == {
        "finding_id", "basis", "evidence_ids"
    }
    forbidden = {
        "score", "quality_score", "session_score", "success", "failure", "verdict",
        "portfolio_credit", "learning", "project_progress", "execution", "payload", "metadata",
    }
    assert forbidden.isdisjoint(field.name for field in fields(OutcomeAssessment))


def test_unconfirmed_execution_is_not_changed_or_upgraded():
    execution = Execution(
        execution_id="execution-1",
        mission_id="mission-1",
        status=ExecutionStatus.UNCONFIRMED,
        actual_start=None,
        actual_end=None,
        actual_duration=None,
    )
    before = asdict(execution)
    validate_outcome_assessment(
        assessment(OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE, findings=()),
        (evidence(),),
    )
    assert asdict(execution) == before
    assert execution.status is ExecutionStatus.UNCONFIRMED
