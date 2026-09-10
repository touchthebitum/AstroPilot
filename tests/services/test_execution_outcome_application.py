from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from decision.mission.night_mission import NightMission
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    FieldOutcomeEvidence,
    ImageOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)
from decision.services.execution_outcome_application import (
    ExecutionOutcomeApplicationError,
    ExecutionOutcomeApplicationService,
)
from decision.services.execution_transition import ExecutionTransitionError


START = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
END = datetime(2026, 9, 11, 1, tzinfo=timezone.utc)
DURATION = timedelta(hours=3)
OBSERVED_AT = datetime(2026, 9, 11, 2, tzinfo=timezone.utc)


def mission(mission_id="mission-1"):
    return NightMission(
        target="M31",
        confidence="HIGH",
        equipment=["setup"],
        site_name="Mont Sujet",
        mission_id=mission_id,
        decision_id="decision-1",
        selection_id="selection-1",
    )


def service(*missions):
    by_id = {item.mission_id: item for item in missions}
    return ExecutionOutcomeApplicationService(
        mission_loader=lambda mission_id: by_id.get(mission_id)
    )


def execution(status, *, execution_id="execution-1", mission_id="mission-1"):
    timing = {
        ExecutionStatus.NOT_STARTED: (None, None, None),
        ExecutionStatus.IN_PROGRESS: (START, None, None),
        ExecutionStatus.COMPLETED: (START, END, DURATION),
        ExecutionStatus.INTERRUPTED: (START, END, DURATION),
        ExecutionStatus.UNCONFIRMED: (None, None, None),
    }[status]
    return Execution(execution_id, mission_id, status, *timing)


def evidence(kind, category, *, execution_id="execution-1", evidence_id="evidence-1"):
    values = {
        "evidence_id": evidence_id,
        "execution_id": execution_id,
        "category": category,
        "observed_at": OBSERVED_AT,
        "source": OutcomeEvidenceSource.USER,
    }
    if kind is AcquisitionOutcomeEvidence:
        values.update(
            actual_capture_duration=timedelta(hours=2),
            usable_integration_duration=timedelta(minutes=90),
        )
    return kind(**values)


def test_provenance_bound_mission_creates_explicit_not_started_execution():
    source_mission = mission()
    before = asdict(source_mission)
    application = service(source_mission)

    created = application.create_execution(
        execution_id="execution-1",
        mission_id="mission-1",
    )

    assert created == execution(ExecutionStatus.NOT_STARTED)
    assert created.actual_start is None
    assert created.actual_end is None
    assert created.actual_duration is None
    assert asdict(source_mission) == before


def test_unknown_mission_fails_without_substituting_another_mission():
    application = service(mission("mission-latest"))

    with pytest.raises(ExecutionOutcomeApplicationError, match="mission_not_found"):
        application.create_execution(
            execution_id="execution-1",
            mission_id="mission-requested",
        )


def test_mission_without_decision_and_selection_provenance_fails_closed():
    unbound = NightMission(target="M31", confidence="HIGH")
    application = service(unbound)

    with pytest.raises(ExecutionOutcomeApplicationError, match="mission_provenance_required"):
        application.create_execution(
            execution_id="execution-1",
            mission_id=unbound.mission_id,
        )


@pytest.mark.parametrize("status", [ExecutionStatus.IN_PROGRESS, ExecutionStatus.COMPLETED])
def test_creation_has_no_initial_state_shortcut(status):
    application = service(mission())

    with pytest.raises(TypeError):
        application.create_execution(
            execution_id="execution-1",
            mission_id="mission-1",
            status=status,
        )


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        (ExecutionStatus.NOT_STARTED, ExecutionStatus.IN_PROGRESS),
        (ExecutionStatus.NOT_STARTED, ExecutionStatus.UNCONFIRMED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.COMPLETED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.INTERRUPTED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.UNCONFIRMED),
    ],
)
def test_existing_transition_contract_runs_through_command_boundary(source, destination):
    application = service(mission())
    application.create_execution(execution_id="execution-1", mission_id="mission-1")
    if source is ExecutionStatus.IN_PROGRESS:
        application.transition_execution(execution(ExecutionStatus.IN_PROGRESS))

    transitioned = application.transition_execution(execution(destination))

    assert transitioned.status is destination
    assert transitioned.execution_id == "execution-1"
    assert transitioned.mission_id == "mission-1"


def test_invalid_and_terminal_transitions_fail_closed_via_v1_43_validator():
    application = service(mission())
    application.create_execution(execution_id="execution-1", mission_id="mission-1")
    with pytest.raises(ExecutionTransitionError, match="execution_transition_not_allowed"):
        application.transition_execution(execution(ExecutionStatus.COMPLETED))

    application.transition_execution(execution(ExecutionStatus.IN_PROGRESS))
    application.transition_execution(execution(ExecutionStatus.COMPLETED))
    with pytest.raises(ExecutionTransitionError, match="execution_transition_not_allowed"):
        application.transition_execution(execution(ExecutionStatus.UNCONFIRMED))


@pytest.mark.parametrize(
    ("kind", "category"),
    [
        (FieldOutcomeEvidence, OutcomeEvidenceCategory.FIELD),
        (TechnicalOutcomeEvidence, OutcomeEvidenceCategory.TECHNICAL),
        (AcquisitionOutcomeEvidence, OutcomeEvidenceCategory.ACQUISITION),
        (ImageOutcomeEvidence, OutcomeEvidenceCategory.IMAGE),
    ],
)
def test_typed_outcome_evidence_is_recorded_without_changing_execution(kind, category):
    application = service(mission())
    created = application.create_execution(
        execution_id="execution-1",
        mission_id="mission-1",
    )
    before = asdict(created)
    record = evidence(kind, category)

    recorded = application.record_outcome_evidence(
        execution_id="execution-1",
        evidence=record,
    )

    assert recorded is record
    assert application.load_execution("execution-1") == created
    assert asdict(created) == before
    assert created.status is ExecutionStatus.NOT_STARTED


def test_execution_and_outcome_loaders_return_exact_typed_instances():
    application = service(mission())
    created = application.create_execution(
        execution_id="execution-1",
        mission_id="mission-1",
    )
    record = evidence(
        AcquisitionOutcomeEvidence,
        OutcomeEvidenceCategory.ACQUISITION,
    )
    application.record_outcome_evidence(
        execution_id="execution-1",
        evidence=record,
    )

    assert application.load_execution("execution-1") is created
    assert application.load_outcome_evidence("evidence-1") is record
    assert application.load_execution("missing") is None
    assert application.load_outcome_evidence("missing") is None


def test_evidence_for_unknown_or_different_execution_fails_closed():
    application = service(mission())
    application.create_execution(execution_id="execution-1", mission_id="mission-1")
    record = evidence(
        FieldOutcomeEvidence,
        OutcomeEvidenceCategory.FIELD,
        execution_id="execution-2",
    )

    with pytest.raises(ExecutionOutcomeApplicationError, match="execution_not_found"):
        application.record_outcome_evidence(execution_id="unknown", evidence=record)
    with pytest.raises(ExecutionOutcomeApplicationError, match="evidence_execution_mismatch"):
        application.record_outcome_evidence(execution_id="execution-1", evidence=record)


def test_evidence_does_not_confirm_unconfirmed_execution_or_create_downstream_objects():
    application = service(mission())
    application.create_execution(execution_id="execution-1", mission_id="mission-1")
    unconfirmed = application.transition_execution(
        execution(ExecutionStatus.UNCONFIRMED)
    )

    application.record_outcome_evidence(
        execution_id="execution-1",
        evidence=evidence(FieldOutcomeEvidence, OutcomeEvidenceCategory.FIELD),
    )

    assert application.load_execution("execution-1") == unconfirmed
    assert unconfirmed.status is ExecutionStatus.UNCONFIRMED
    assert not hasattr(application, "portfolio_credit")
    assert not hasattr(application, "outcome_assessment")
    assert not hasattr(application, "learning")
