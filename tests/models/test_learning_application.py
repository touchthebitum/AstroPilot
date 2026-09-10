from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timezone
import inspect

import pytest

from decision.models.learning_application import (
    LearningApplication,
    LearningApplicationOutcome,
    LearningApplicationResult,
)
from decision.models.learning_eligibility import (
    LearnableDimension,
    LearningEligibility,
    LearningEligibilityReason,
    LearningEligibilityReasonCode,
    LearningEligibilityStatus,
)
from decision.models.learning_signal import LearningSignal
from decision.services import learning_application
from decision.services.learning_application import apply_learning_signal


AT = datetime(2026, 9, 10, 23, tzinfo=timezone.utc)


def eligibility(execution_id="execution-1", assessment_id="assessment-1"):
    return LearningEligibility(
        execution_id=execution_id,
        assessment_id=assessment_id,
        status=LearningEligibilityStatus.ELIGIBLE,
        reasons=(LearningEligibilityReason(
            code=LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING,
            dimension=LearnableDimension.TECHNICAL,
            finding_id="finding-1",
            evidence_ids=("evidence-1",),
        ),),
    )


def signal(
    signal_id="signal-1",
    execution_id="execution-1",
    assessment_id="assessment-1",
):
    return LearningSignal(
        signal_id=signal_id,
        execution_id=execution_id,
        assessment_id=assessment_id,
        eligibility=eligibility(execution_id, assessment_id),
        dimension=LearnableDimension.TECHNICAL,
        evidence_ids=("evidence-1",),
        created_at=AT,
    )


def application(application_id="application-1", signal_id="signal-1", applied_at=AT):
    return LearningApplication(
        application_id=application_id,
        signal_id=signal_id,
        applied_at=applied_at,
    )


def test_valid_first_learning_application_is_traceably_recorded():
    applications = {}
    source_signal = signal()
    source_application = application()
    result = apply_learning_signal(source_application, source_signal, applications)
    assert result == LearningApplicationResult(
        application=source_application,
        outcome=LearningApplicationOutcome.APPLIED,
    )
    assert applications == {source_signal.signal_id: source_application}
    assert result.application.signal_id == source_signal.signal_id


@pytest.mark.parametrize("name", ["application_id", "signal_id"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 1, True, (), {}])
def test_application_and_signal_identifiers_required(name, value):
    with pytest.raises((TypeError, ValueError)):
        application(**{name: value})


def test_signal_id_mismatch_rejected_without_recording():
    applications = {}
    with pytest.raises(ValueError, match="signal_id_mismatch"):
        apply_learning_signal(application(signal_id="signal-2"), signal(), applications)
    assert applications == {}


@pytest.mark.parametrize("value", [datetime(2026, 9, 10, 23), None, "now", 0, {}])
def test_timezone_naive_or_malformed_applied_at_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        application(applied_at=value)


def test_learning_signal_remains_immutable_and_unmodified():
    source_signal = signal()
    before = asdict(source_signal)
    apply_learning_signal(application(), source_signal, {})
    assert asdict(source_signal) == before
    with pytest.raises(FrozenInstanceError):
        source_signal.signal_id = "changed"


def test_same_signal_repeatedly_is_idempotent_and_returns_original_application():
    applications = {}
    source_signal = signal()
    original = application()
    first = apply_learning_signal(original, source_signal, applications)
    assert first.outcome is LearningApplicationOutcome.APPLIED
    for attempt in (
        original,
        application("application-2", applied_at=datetime(2026, 9, 11, tzinfo=timezone.utc)),
        application("application-3", applied_at=datetime(2026, 9, 12, tzinfo=timezone.utc)),
    ):
        result = apply_learning_signal(attempt, source_signal, applications)
        assert result.outcome is LearningApplicationOutcome.ALREADY_APPLIED
        assert result.application is original
        assert applications == {"signal-1": original}


@pytest.mark.parametrize("same_attribute", ["execution", "assessment", "dimension", "evidence"])
def test_distinct_signal_ids_are_not_deduplicated_by_other_provenance(same_attribute):
    applications = {}
    first_signal = signal("signal-1")
    second_signal = signal("signal-2")
    first = apply_learning_signal(application("application-1", "signal-1"), first_signal, applications)
    second = apply_learning_signal(application("application-2", "signal-2"), second_signal, applications)
    assert first.outcome is LearningApplicationOutcome.APPLIED
    assert second.outcome is LearningApplicationOutcome.APPLIED
    assert set(applications) == {"signal-1", "signal-2"}
    assert first_signal.execution_id == second_signal.execution_id
    assert first_signal.assessment_id == second_signal.assessment_id
    assert first_signal.dimension is second_signal.dimension
    assert first_signal.evidence_ids == second_signal.evidence_ids


def test_no_destination_is_inferred_or_fabricated_when_none_exists():
    assert {field.name for field in fields(LearningApplication)} == {
        "application_id", "signal_id", "applied_at"
    }
    with pytest.raises(TypeError):
        LearningApplication(
            application_id="application-1",
            signal_id="signal-1",
            applied_at=AT,
            destination="technical",
        )


def test_inconsistent_application_registry_fails_closed():
    applications = {"wrong-key": application()}
    with pytest.raises(ValueError, match="application_state_inconsistent"):
        apply_learning_signal(application(), signal(), applications)
    assert applications == {"wrong-key": application()}


def test_application_requires_learning_signal_and_cannot_bypass_it():
    with pytest.raises(TypeError, match="signal_must_be_learning_signal"):
        apply_learning_signal(application(), eligibility(), {})
    assert set(inspect.signature(apply_learning_signal).parameters) == {
        "application", "signal", "applications_by_signal_id"
    }


def test_learning_application_and_result_are_immutable():
    source_application = application()
    result = LearningApplicationResult(
        application=source_application,
        outcome=LearningApplicationOutcome.APPLIED,
    )
    for item in (source_application, result):
        for field in fields(item):
            with pytest.raises(FrozenInstanceError):
                setattr(item, field.name, getattr(item, field.name))


@pytest.mark.parametrize("missing", ["application_id", "signal_id", "applied_at"])
def test_no_hidden_identifier_or_current_time_defaults(missing):
    values = {
        "application_id": "application-1",
        "signal_id": "signal-1",
        "applied_at": AT,
    }
    del values[missing]
    with pytest.raises(TypeError):
        LearningApplication(**values)


def test_service_has_no_policy_ranking_scoring_weather_or_signal_mutation_surface():
    source = inspect.getsource(learning_application)
    for forbidden in (
        "OutcomeAssessment", "OutcomeEvidence", "Execution", "LearningEligibility",
        "PortfolioCredit", "Recommendation", "policy", "ranking", "scoring",
        "WeatherTrust", "reward", "penalty", "destination", "datetime.now", "utcnow",
    ):
        assert forbidden not in source
