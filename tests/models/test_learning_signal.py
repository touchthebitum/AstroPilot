from dataclasses import FrozenInstanceError, asdict, fields, replace
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
from decision.models.learning_signal import LearningSignal
from decision.models.outcome_assessment import (
    OutcomeAssessment,
    OutcomeAssessmentStatus,
    OutcomeFinding,
)
from decision.models.outcome_evidence import (
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)
from decision.services import learning_signal_validation
from decision.services.learning_eligibility_evaluator import evaluate_learning_eligibility
from decision.services.learning_signal_validation import validate_learning_signal


AT = datetime(2026, 9, 10, 23, tzinfo=timezone.utc)


def execution(execution_id="execution-1"):
    return Execution(
        execution_id=execution_id,
        mission_id="mission-1",
        status=ExecutionStatus.COMPLETED,
        actual_start=AT - timedelta(hours=1),
        actual_end=AT,
        actual_duration=timedelta(hours=1),
    )


def evidence(evidence_id="evidence-1", execution_id="execution-1"):
    return TechnicalOutcomeEvidence(
        evidence_id=evidence_id,
        execution_id=execution_id,
        category=OutcomeEvidenceCategory.TECHNICAL,
        observed_at=AT,
        source=OutcomeEvidenceSource.USER,
    )


def assessment(
    assessment_id="assessment-1",
    execution_id="execution-1",
    finding_basis=LearnableDimension.TECHNICAL.value,
):
    return OutcomeAssessment(
        assessment_id=assessment_id,
        execution_id=execution_id,
        evidence_ids=("evidence-1",),
        assessed_at=AT,
        status=OutcomeAssessmentStatus.SUFFICIENT,
        findings=(OutcomeFinding(
            finding_id="finding-1",
            basis=finding_basis,
            evidence_ids=("evidence-1",),
        ),),
    )


def eligible(source_assessment=None, source_evidence=None):
    source_assessment = source_assessment or assessment()
    source_evidence = source_evidence or evidence()
    return evaluate_learning_eligibility(
        execution(source_assessment.execution_id), source_assessment, (source_evidence,)
    )


def signal(source_eligibility=None, **changes):
    source_eligibility = source_eligibility or eligible()
    values = {
        "signal_id": "signal-1",
        "execution_id": "execution-1",
        "assessment_id": "assessment-1",
        "eligibility": source_eligibility,
        "dimension": LearnableDimension.TECHNICAL,
        "evidence_ids": ("evidence-1",),
        "created_at": AT,
    }
    values.update(changes)
    return LearningSignal(**values)


def test_valid_learning_signal_from_eligible_provenance():
    source_assessment = assessment()
    source_evidence = evidence()
    source_eligibility = eligible(source_assessment, source_evidence)
    record = signal(source_eligibility)
    assert validate_learning_signal(
        record, source_eligibility, source_assessment, (source_evidence,)
    ) is record


@pytest.mark.parametrize("status,reason", [
    (
        LearningEligibilityStatus.NOT_ELIGIBLE,
        LearningEligibilityReason(LearningEligibilityReasonCode.NO_SUPPORTED_LEARNABLE_FINDING),
    ),
    (
        LearningEligibilityStatus.INSUFFICIENT_EVIDENCE,
        LearningEligibilityReason(
            LearningEligibilityReasonCode.ASSESSMENT_INSUFFICIENT_EVIDENCE
        ),
    ),
])
def test_non_eligible_status_cannot_produce_signal(status, reason):
    source_eligibility = LearningEligibility(
        execution_id="execution-1",
        assessment_id="assessment-1",
        status=status,
        reasons=(reason,),
    )
    with pytest.raises(ValueError, match="eligible_learning_eligibility_required"):
        signal(source_eligibility)


@pytest.mark.parametrize("name", ["signal_id", "execution_id", "assessment_id"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 1, True, (), {}])
def test_empty_or_malformed_signal_provenance_identifiers_rejected(name, value):
    with pytest.raises((TypeError, ValueError)):
        signal(**{name: value})


@pytest.mark.parametrize("value", [datetime(2026, 9, 10, 23), None, "now", 0, {}])
def test_timezone_naive_or_malformed_created_at_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        signal(created_at=value)


def test_signal_execution_must_match_eligibility_and_assessment():
    with pytest.raises(ValueError, match="eligibility_execution_mismatch"):
        signal(execution_id="execution-2")

    source_assessment = assessment(execution_id="execution-2")
    source_evidence = evidence(execution_id="execution-2")
    source_eligibility = eligible(source_assessment, source_evidence)
    record = signal(
        source_eligibility,
        execution_id="execution-2",
        assessment_id=source_assessment.assessment_id,
    )
    with pytest.raises(ValueError, match="assessment_execution_mismatch"):
        validate_learning_signal(
            record, source_eligibility, assessment(), (source_evidence,)
        )


def test_signal_assessment_must_match_eligibility_and_supplied_assessment():
    with pytest.raises(ValueError, match="eligibility_assessment_mismatch"):
        signal(assessment_id="assessment-2")

    record = signal()
    with pytest.raises(ValueError, match="assessment_id_mismatch"):
        validate_learning_signal(record, record.eligibility, assessment("assessment-2"), (evidence(),))


def test_cross_execution_evidence_rejected():
    record = signal()
    with pytest.raises(ValueError, match="evidence_execution_mismatch"):
        validate_learning_signal(
            record, record.eligibility, assessment(), (evidence(execution_id="execution-2"),)
        )


def test_unsupported_unrelated_or_duplicate_evidence_rejected():
    record = signal()
    with pytest.raises(ValueError, match="evidence_records_mismatch"):
        validate_learning_signal(record, record.eligibility, assessment(), ())
    with pytest.raises(ValueError, match="evidence_records_mismatch"):
        validate_learning_signal(
            record,
            record.eligibility,
            assessment(),
            (evidence(), evidence("evidence-2")),
        )
    item = evidence()
    with pytest.raises(ValueError, match="duplicate_evidence_record"):
        validate_learning_signal(record, record.eligibility, assessment(), (item, item))


@pytest.mark.parametrize("evidence_ids", [
    (),
    ("evidence-1", "evidence-1"),
    ("evidence-1", ""),
    ("evidence-1", 1),
    ["evidence-1"],
    "evidence-1",
    None,
])
def test_signal_evidence_provenance_must_be_explicit_and_unambiguous(evidence_ids):
    with pytest.raises((TypeError, ValueError)):
        signal(evidence_ids=evidence_ids)


def test_only_dimension_explicitly_allowed_by_eligibility_is_accepted():
    with pytest.raises(TypeError):
        signal(dimension="technical")
    assert {member.name for member in LearnableDimension} == {"TECHNICAL"}


def test_free_form_finding_text_cannot_infer_another_dimension_or_signal():
    source_assessment = assessment(finding_basis="excellent guiding result")
    source_evidence = evidence()
    source_eligibility = evaluate_learning_eligibility(
        execution(), source_assessment, (source_evidence,)
    )
    assert source_eligibility.status is LearningEligibilityStatus.NOT_ELIGIBLE
    with pytest.raises(ValueError, match="eligible_learning_eligibility_required"):
        signal(source_eligibility)


def test_signal_cannot_be_validated_without_matching_eligible_source():
    record = signal()
    with pytest.raises(TypeError):
        validate_learning_signal(record, assessment(), assessment(), (evidence(),))
    different_eligibility = replace(
        record.eligibility,
        reasons=(LearningEligibilityReason(
            code=LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING,
            dimension=LearnableDimension.TECHNICAL,
            finding_id="finding-2",
            evidence_ids=("evidence-1",),
        ),),
    )
    with pytest.raises(ValueError, match="eligibility_provenance_mismatch"):
        validate_learning_signal(record, different_eligibility, assessment(), (evidence(),))


def test_assessment_finding_path_cannot_be_broadened_or_replaced():
    record = signal()
    changed_assessment = OutcomeAssessment(
        assessment_id="assessment-1",
        execution_id="execution-1",
        evidence_ids=("evidence-1",),
        assessed_at=AT,
        status=OutcomeAssessmentStatus.SUFFICIENT,
        findings=(OutcomeFinding(
            finding_id="finding-2",
            basis=LearnableDimension.TECHNICAL.value,
            evidence_ids=("evidence-1",),
        ),),
    )
    with pytest.raises(ValueError, match="eligibility_finding_provenance_mismatch"):
        validate_learning_signal(
            record, record.eligibility, changed_assessment, (evidence(),)
        )


def test_source_objects_remain_immutable_and_unmodified():
    source_assessment = assessment()
    source_evidence = evidence()
    source_eligibility = eligible(source_assessment, source_evidence)
    record = signal(source_eligibility)
    before = tuple(asdict(item) for item in (
        source_eligibility, source_assessment, source_evidence
    ))
    validate_learning_signal(
        record, source_eligibility, source_assessment, (source_evidence,)
    )
    after = tuple(asdict(item) for item in (
        source_eligibility, source_assessment, source_evidence
    ))
    assert after == before


def test_learning_signal_is_immutable():
    record = signal()
    for field in fields(record):
        with pytest.raises(FrozenInstanceError):
            setattr(record, field.name, getattr(record, field.name))


@pytest.mark.parametrize("missing", [
    "signal_id", "execution_id", "assessment_id", "eligibility",
    "dimension", "evidence_ids", "created_at",
])
def test_no_hidden_provenance_or_current_time_defaults(missing):
    source_eligibility = eligible()
    values = {
        "signal_id": "signal-1",
        "execution_id": "execution-1",
        "assessment_id": "assessment-1",
        "eligibility": source_eligibility,
        "dimension": LearnableDimension.TECHNICAL,
        "evidence_ids": ("evidence-1",),
        "created_at": AT,
    }
    del values[missing]
    with pytest.raises(TypeError):
        LearningSignal(**values)


def test_signal_contract_has_no_speculative_learning_fields():
    assert {field.name for field in fields(LearningSignal)} == {
        "signal_id", "execution_id", "assessment_id", "eligibility",
        "dimension", "evidence_ids", "created_at",
    }
    forbidden = {
        "score", "polarity", "reward", "penalty", "confidence", "provider_weight",
        "target_weight", "ranking_delta", "scoring_delta", "policy_adjustment",
        "trust_adjustment", "learning_rate", "payload", "metadata", "application",
    }
    assert forbidden.isdisjoint(field.name for field in fields(LearningSignal))


def test_validator_has_no_learning_application_or_mutation_surface():
    assert set(inspect.signature(validate_learning_signal).parameters) == {
        "signal", "eligibility", "assessment", "evidence_records"
    }
    source = inspect.getsource(learning_signal_validation)
    for forbidden in (
        "LearningApplication", "policy", "ranking", "scoring", "WeatherTrust",
        "Recommendation", "PortfolioCredit", "datetime.now", "utcnow",
        "evaluate_learning_eligibility",
    ):
        assert forbidden not in source
