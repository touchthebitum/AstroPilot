from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timedelta, timezone
import inspect

import pytest

from decision.models.portfolio_credit import PortfolioCredit
from decision.models.portfolio_credit_application import (
    PortfolioCreditApplication,
    PortfolioCreditApplicationOutcome,
    PortfolioCreditApplicationResult,
    PortfolioCreditDestinationKind,
)
from decision.services import portfolio_credit_application
from decision.services.portfolio_credit_application import apply_portfolio_credit


APPLIED_AT = datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc)


def credit(credit_id="credit-1", duration=timedelta(minutes=30)):
    return PortfolioCredit(
        credit_id=credit_id,
        execution_id="execution-1",
        evidence_ids=(f"evidence-{credit_id}",),
        usable_integration_duration=duration,
        credited_at=APPLIED_AT,
    )


def application(
    application_id="application-1",
    credit_id="credit-1",
    object_name="M31",
    destination_kind=PortfolioCreditDestinationKind.PROJECT,
    duration=timedelta(minutes=30),
    applied_at=APPLIED_AT,
):
    return PortfolioCreditApplication(
        application_id=application_id,
        credit_id=credit_id,
        object_name=object_name,
        destination_kind=destination_kind,
        applied_duration=duration,
        applied_at=applied_at,
    )


def project(hours=2.0):
    return {"hours": hours, "target_hours": 10.0, "importance": 8, "quality": "existing"}


def test_first_positive_credit_application_increases_project_hours_exactly_once():
    projects = {"M31": project()}
    applications = {}
    result = apply_portfolio_credit(application(), credit(), projects, applications)
    assert result == PortfolioCreditApplicationResult(
        application=application(), outcome=PortfolioCreditApplicationOutcome.APPLIED
    )
    assert projects["M31"]["hours"] == 2.5
    assert applications == {"credit-1": application()}
    assert result.application.applied_duration == credit().usable_integration_duration


def test_same_credit_repeatedly_is_idempotent_and_returns_recorded_application():
    projects = {"M31": project()}
    applications = {}
    original = application()
    first = apply_portfolio_credit(original, credit(), projects, applications)
    assert first.outcome is PortfolioCreditApplicationOutcome.APPLIED
    for attempt in (
        original,
        application("application-2", object_name="M42"),
        application("application-3", destination_kind=PortfolioCreditDestinationKind.TARGET),
    ):
        result = apply_portfolio_credit(attempt, credit(), projects, applications)
        assert result.outcome is PortfolioCreditApplicationOutcome.ALREADY_APPLIED
        assert result.application is original
        assert projects["M31"]["hours"] == 2.5
        assert "M42" not in projects
        assert len(applications) == 1


def test_distinct_credit_ids_with_same_duration_both_apply():
    projects = {"M31": project()}
    applications = {}
    apply_portfolio_credit(application(), credit(), projects, applications)
    apply_portfolio_credit(
        application("application-2", "credit-2"),
        credit("credit-2"),
        projects,
        applications,
    )
    assert projects["M31"]["hours"] == 3.0
    assert set(applications) == {"credit-1", "credit-2"}


def test_zero_duration_credit_is_traceable_without_increasing_hours():
    projects = {"M31": project()}
    applications = {}
    zero = timedelta(0)
    result = apply_portfolio_credit(
        application(duration=zero), credit(duration=zero), projects, applications
    )
    assert result.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert result.application.applied_duration == zero
    assert applications["credit-1"] is result.application
    assert projects["M31"]["hours"] == 2.0


@pytest.mark.parametrize("duration", [timedelta(microseconds=-1), -1, 0, True, None, "30", {}])
def test_negative_or_malformed_application_duration_rejected(duration):
    with pytest.raises((TypeError, ValueError)):
        application(duration=duration)


def test_applied_duration_mismatch_rejected_without_mutation():
    projects = {"M31": project()}
    applications = {}
    before = {name: values.copy() for name, values in projects.items()}
    with pytest.raises(ValueError, match="applied_duration_mismatch"):
        apply_portfolio_credit(
            application(duration=timedelta(minutes=20)), credit(), projects, applications
        )
    assert projects == before
    assert applications == {}


def test_credit_id_mismatch_rejected_without_mutation():
    projects = {"M31": project()}
    applications = {}
    before = {name: values.copy() for name, values in projects.items()}
    with pytest.raises(ValueError, match="credit_id_mismatch"):
        apply_portfolio_credit(application(credit_id="credit-2"), credit(), projects, applications)
    assert projects == before
    assert applications == {}


@pytest.mark.parametrize("name", ["application_id", "credit_id", "object_name"])
@pytest.mark.parametrize("value", ["", " \t\n", None, 1, True, (), {}])
def test_empty_or_malformed_identifiers_rejected(name, value):
    with pytest.raises((TypeError, ValueError)):
        application(**{name: value})


@pytest.mark.parametrize("value", [datetime(2026, 9, 10, 23, 30), None, 0, "now"])
def test_timezone_naive_or_malformed_applied_at_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        application(applied_at=value)


def test_explicit_project_destination_mutates_only_correct_project():
    projects = {"M31": project(1.0), "M42": project(4.0)}
    applications = {}
    apply_portfolio_credit(application(object_name="M42"), credit(), projects, applications)
    assert projects["M31"]["hours"] == 1.0
    assert projects["M42"]["hours"] == 4.5


def test_target_only_discovery_destination_is_traceable_without_fabricating_project():
    projects = {"M31": project()}
    applications = {}
    target_application = application(
        object_name="NGC 7000", destination_kind=PortfolioCreditDestinationKind.TARGET
    )
    result = apply_portfolio_credit(target_application, credit(), projects, applications)
    assert result.outcome is PortfolioCreditApplicationOutcome.APPLIED
    assert applications["credit-1"] is target_application
    assert "NGC 7000" not in projects
    assert projects == {"M31": project()}


def test_unresolved_project_destination_fails_closed_without_guessing():
    projects = {"M31": project()}
    applications = {}
    before = {name: values.copy() for name, values in projects.items()}
    with pytest.raises(ValueError, match="project_destination_unresolved"):
        apply_portfolio_credit(
            application(object_name="NGC 7000"), credit(), projects, applications
        )
    assert projects == before
    assert applications == {}


def test_credit_application_does_not_mutate_credit_or_project_priority_quality():
    source_credit = credit()
    before_credit = asdict(source_credit)
    projects = {"M31": project()}
    before_priority = projects["M31"]["importance"]
    before_quality = projects["M31"]["quality"]
    apply_portfolio_credit(application(), source_credit, projects, {})
    assert asdict(source_credit) == before_credit
    assert projects["M31"]["importance"] == before_priority
    assert projects["M31"]["quality"] == before_quality


def test_inconsistent_existing_application_state_fails_closed():
    projects = {"M31": project()}
    applications = {"wrong-key": application()}
    before = {name: values.copy() for name, values in projects.items()}
    with pytest.raises(ValueError, match="application_state_inconsistent"):
        apply_portfolio_credit(application(), credit(), projects, applications)
    assert projects == before
    assert applications == {"wrong-key": application()}


def test_existing_credit_with_inconsistent_duration_fails_closed():
    projects = {"M31": project(2.5)}
    applications = {"credit-1": application(duration=timedelta(minutes=20))}
    before = {name: values.copy() for name, values in projects.items()}
    with pytest.raises(ValueError, match="application_state_inconsistent"):
        apply_portfolio_credit(application(), credit(), projects, applications)
    assert projects == before


def test_application_and_result_are_immutable():
    source_application = application()
    result = PortfolioCreditApplicationResult(
        source_application, PortfolioCreditApplicationOutcome.APPLIED
    )
    for item in (source_application, result):
        for field in fields(item):
            with pytest.raises(FrozenInstanceError):
                setattr(item, field.name, getattr(item, field.name))


@pytest.mark.parametrize("missing", [
    "application_id", "credit_id", "object_name", "destination_kind", "applied_duration", "applied_at"
])
def test_no_hidden_provenance_duration_or_time_defaults(missing):
    values = {
        "application_id": "application-1",
        "credit_id": "credit-1",
        "object_name": "M31",
        "destination_kind": PortfolioCreditDestinationKind.PROJECT,
        "applied_duration": timedelta(minutes=30),
        "applied_at": APPLIED_AT,
    }
    del values[missing]
    with pytest.raises(TypeError):
        PortfolioCreditApplication(**values)


@pytest.mark.parametrize("value", ["project", "target", None, 1, {}])
def test_untyped_or_unsupported_destination_kind_rejected(value):
    with pytest.raises(TypeError):
        application(destination_kind=value)


def test_service_has_no_outcome_assessment_learning_or_unrelated_domain_dependency():
    parameters = set(inspect.signature(apply_portfolio_credit).parameters)
    assert parameters == {"application", "credit", "projects", "applications_by_credit_id"}
    source = inspect.getsource(portfolio_credit_application)
    for forbidden in (
        "OutcomeAssessment", "Execution", "OutcomeEvidence", "Mission", "UserSelection",
        "Recommendation", "Learning", "ranking", "scoring",
    ):
        assert forbidden not in source
