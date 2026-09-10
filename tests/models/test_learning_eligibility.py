from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timedelta, timezone
import inspect

import pytest

from decision.models.execution import Execution, ExecutionStatus
from decision.models.learning_eligibility import (
    LearnableDimension,
    LearningEligibility,
    LearningEligibilityReason,
    LearningEligibilityReasonCode,
    LearningEligibilityStatus,
)
from decision.models.outcome_assessment import (
    OutcomeAssessment,
    OutcomeAssessmentStatus,
    OutcomeFinding,
)
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)
from decision.models.portfolio_credit import PortfolioCredit
from decision.services import learning_eligibility_evaluator
from decision.services.learning_eligibility_evaluator import evaluate_learning_eligibility


AT = datetime(2026, 9, 10, 23, tzinfo=timezone.utc)


def execution(status=ExecutionStatus.COMPLETED, execution_id="execution-1"):
    if status in (ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED):
        return Execution(
            execution_id, "mission-1", status, AT - timedelta(hours=1), AT, timedelta(hours=1)
        )
    if status is ExecutionStatus.IN_PROGRESS:
        return Execution(execution_id, "mission-1", status, AT, None, None)
    return Execution(execution_id, "mission-1", status, None, None, None)


def technical_evidence(evidence_id="evidence-1", execution_id="execution-1"):
    return TechnicalOutcomeEvidence(
        evidence_id=evidence_id,
        execution_id=execution_id,
        category=OutcomeEvidenceCategory.TECHNICAL,
        observed_at=AT,
        source=OutcomeEvidenceSource.USER,
    )


def acquisition_evidence(evidence_id="evidence-2", usable=timedelta(0)):
    return AcquisitionOutcomeEvidence(
        evidence_id=evidence_id,
        execution_id="execution-1",
        category=OutcomeEvidenceCategory.ACQUISITION,
        observed_at=AT,
        source=OutcomeEvidenceSource.USER,
        usable_integration_duration=usable,
    )


def assessment(
    status=OutcomeAssessmentStatus.SUFFICIENT,
    basis=LearnableDimension.TECHNICAL.value,
    execution_id="execution-1",
    evidence_ids=("evidence-1",),
    findings=None,
):
    if findings is None:
        findings = (
            OutcomeFinding(
                finding_id="finding-1",
                basis=basis,
                evidence_ids=("evidence-1",),
            ),
        )
    return OutcomeAssessment(
        assessment_id="assessment-1",
        execution_id=execution_id,
        evidence_ids=evidence_ids,
        assessed_at=AT,
        status=status,
        findings=findings,
    )


@pytest.mark.parametrize("status,reason_code", [
    (ExecutionStatus.NOT_STARTED, LearningEligibilityReasonCode.EXECUTION_NOT_STARTED),
    (ExecutionStatus.IN_PROGRESS, LearningEligibilityReasonCode.EXECUTION_IN_PROGRESS),
    (ExecutionStatus.UNCONFIRMED, LearningEligibilityReasonCode.EXECUTION_UNCONFIRMED),
])
def test_open_or_unconfirmed_execution_is_not_eligible(status, reason_code):
    result = evaluate_learning_eligibility(execution(status))
    assert result.status is LearningEligibilityStatus.NOT_ELIGIBLE
    assert result.assessment_id is None
    assert result.reasons == (LearningEligibilityReason(code=reason_code),)


@pytest.mark.parametrize("status", [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED])
def test_closed_execution_alone_cannot_establish_eligibility(status):
    with pytest.raises(ValueError, match="assessment_required"):
        evaluate_learning_eligibility(execution(status))


def test_insufficient_evidence_assessment_remains_non_judgmental():
    source_assessment = assessment(
        status=OutcomeAssessmentStatus.INSUFFICIENT_EVIDENCE, findings=()
    )
    result = evaluate_learning_eligibility(
        execution(), source_assessment, (technical_evidence(),)
    )
    assert result.status is LearningEligibilityStatus.INSUFFICIENT_EVIDENCE
    assert result.reasons == (
        LearningEligibilityReason(
            code=LearningEligibilityReasonCode.ASSESSMENT_INSUFFICIENT_EVIDENCE
        ),
    )
    assert all(word not in result.status.value for word in ("failure", "poor", "bad"))


@pytest.mark.parametrize("status", [OutcomeAssessmentStatus.PARTIAL, OutcomeAssessmentStatus.SUFFICIENT])
def test_assessment_without_explicit_learnable_finding_is_not_eligible(status):
    source_assessment = assessment(status=status, basis="field_observation_recorded")
    result = evaluate_learning_eligibility(
        execution(), source_assessment, (technical_evidence(),)
    )
    assert result.status is LearningEligibilityStatus.NOT_ELIGIBLE
    assert result.reasons == (
        LearningEligibilityReason(
            code=LearningEligibilityReasonCode.NO_SUPPORTED_LEARNABLE_FINDING
        ),
    )


@pytest.mark.parametrize("execution_status", [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED])
def test_closed_execution_with_explicit_supported_learnable_finding_is_eligible(execution_status):
    result = evaluate_learning_eligibility(
        execution(execution_status), assessment(), (technical_evidence(),)
    )
    assert result.status is LearningEligibilityStatus.ELIGIBLE
    assert result.assessment_id == "assessment-1"
    assert result.reasons == (
        LearningEligibilityReason(
            code=LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING,
            dimension=LearnableDimension.TECHNICAL,
            finding_id="finding-1",
            evidence_ids=("evidence-1",),
        ),
    )


def test_partial_assessment_with_explicit_supported_finding_can_be_eligible():
    result = evaluate_learning_eligibility(
        execution(),
        assessment(status=OutcomeAssessmentStatus.PARTIAL),
        (technical_evidence(),),
    )
    assert result.status is LearningEligibilityStatus.ELIGIBLE


def test_zero_usable_integration_does_not_prevent_eligibility():
    source_assessment = assessment(evidence_ids=("evidence-1", "evidence-2"))
    result = evaluate_learning_eligibility(
        execution(), source_assessment, (technical_evidence(), acquisition_evidence())
    )
    assert result.status is LearningEligibilityStatus.ELIGIBLE


def test_positive_portfolio_credit_does_not_cause_eligibility():
    source_assessment = assessment(basis="acquisition_recorded")
    source_credit = PortfolioCredit(
        credit_id="credit-1",
        execution_id="execution-1",
        evidence_ids=("evidence-2",),
        usable_integration_duration=timedelta(minutes=45),
        credited_at=AT,
    )
    credit_before = asdict(source_credit)
    result = evaluate_learning_eligibility(
        execution(), source_assessment, (technical_evidence(),)
    )
    assert result.status is LearningEligibilityStatus.NOT_ELIGIBLE
    assert asdict(source_credit) == credit_before
    assert "credit" not in inspect.signature(evaluate_learning_eligibility).parameters


@pytest.mark.parametrize("basis", [
    "technical issue observed",
    "excellent technical result",
    "bad session",
    "TECHNICAL",
    " technical ",
])
def test_free_form_finding_text_cannot_establish_learnability(basis):
    result = evaluate_learning_eligibility(
        execution(), assessment(basis=basis), (technical_evidence(),)
    )
    assert result.status is LearningEligibilityStatus.NOT_ELIGIBLE


def test_technical_basis_without_typed_technical_support_is_not_eligible():
    source_assessment = assessment(evidence_ids=("evidence-2",), findings=(
        OutcomeFinding("finding-1", LearnableDimension.TECHNICAL.value, ("evidence-2",)),
    ))
    result = evaluate_learning_eligibility(
        execution(), source_assessment, (acquisition_evidence(),)
    )
    assert result.status is LearningEligibilityStatus.NOT_ELIGIBLE


def test_cross_execution_assessment_and_evidence_are_rejected():
    with pytest.raises(ValueError, match="assessment_execution_mismatch"):
        evaluate_learning_eligibility(
            execution(), assessment(execution_id="execution-2"),
            (technical_evidence(execution_id="execution-2"),),
        )
    with pytest.raises(ValueError, match="evidence_execution_mismatch"):
        evaluate_learning_eligibility(
            execution(), assessment(), (technical_evidence(execution_id="execution-2"),)
        )


def test_source_execution_assessment_and_evidence_remain_unmodified():
    source_execution = execution(ExecutionStatus.INTERRUPTED)
    source_assessment = assessment()
    source_evidence = technical_evidence()
    before = tuple(asdict(item) for item in (source_execution, source_assessment, source_evidence))
    evaluate_learning_eligibility(source_execution, source_assessment, (source_evidence,))
    after = tuple(asdict(item) for item in (source_execution, source_assessment, source_evidence))
    assert after == before


def test_learning_eligibility_and_reasons_are_immutable_and_structured():
    result = evaluate_learning_eligibility(execution(), assessment(), (technical_evidence(),))
    assert {member.name for member in LearningEligibilityStatus} == {
        "ELIGIBLE", "NOT_ELIGIBLE", "INSUFFICIENT_EVIDENCE"
    }
    assert {member.name for member in LearnableDimension} == {"TECHNICAL"}
    assert isinstance(result.reasons, tuple)
    assert all(type(reason) is LearningEligibilityReason for reason in result.reasons)
    assert all(isinstance(reason.code, LearningEligibilityReasonCode) for reason in result.reasons)
    for item in (result, result.reasons[0]):
        for field in fields(item):
            with pytest.raises(FrozenInstanceError):
                setattr(item, field.name, getattr(item, field.name))


@pytest.mark.parametrize("value", ["", "  ", None, 1, True, (), {}])
def test_learning_eligibility_rejects_empty_execution_id(value):
    with pytest.raises((TypeError, ValueError)):
        LearningEligibility(
            execution_id=value,
            assessment_id=None,
            status=LearningEligibilityStatus.NOT_ELIGIBLE,
            reasons=(LearningEligibilityReason(
                LearningEligibilityReasonCode.EXECUTION_NOT_STARTED
            ),),
        )


def test_assessment_id_may_be_absent_only_for_execution_state_decisions():
    with pytest.raises(ValueError, match="assessment_id_required"):
        LearningEligibility(
            execution_id="execution-1",
            assessment_id=None,
            status=LearningEligibilityStatus.ELIGIBLE,
            reasons=(LearningEligibilityReason(
                code=LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING,
                dimension=LearnableDimension.TECHNICAL,
                finding_id="finding-1",
                evidence_ids=("evidence-1",),
            ),),
        )


def test_no_hidden_time_identifier_or_other_provenance_defaults():
    assert {field.name for field in fields(LearningEligibility)} == {
        "execution_id", "assessment_id", "status", "reasons"
    }
    with pytest.raises(TypeError):
        LearningEligibility(
            execution_id="execution-1",
            assessment_id=None,
            status=LearningEligibilityStatus.NOT_ELIGIBLE,
        )
    source = inspect.getsource(learning_eligibility_evaluator)
    assert "datetime" not in source
    assert "PortfolioCredit" not in source


def test_no_learning_policy_ranking_or_weather_trust_mutation_surface():
    assert set(inspect.signature(evaluate_learning_eligibility).parameters) == {
        "execution", "assessment", "evidence_records"
    }
    source = inspect.getsource(learning_eligibility_evaluator)
    for forbidden in (
        "LearningRecord", "policy", "ranking", "scoring", "WeatherTrust",
        "Recommendation", "PortfolioCreditApplication",
    ):
        assert forbidden not in source
