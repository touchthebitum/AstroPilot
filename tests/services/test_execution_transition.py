from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from decision.models.execution import Execution, ExecutionStatus
from decision.services.execution_transition import (
    ExecutionTransitionError,
    validate_execution_transition,
)


START = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
END = datetime(2026, 9, 11, 1, tzinfo=timezone.utc)
DURATION = timedelta(hours=3)


def execution(
    status,
    *,
    execution_id="execution-1",
    mission_id="mission-1",
):
    timing = {
        ExecutionStatus.NOT_STARTED: (None, None, None),
        ExecutionStatus.IN_PROGRESS: (START, None, None),
        ExecutionStatus.COMPLETED: (START, END, DURATION),
        ExecutionStatus.INTERRUPTED: (START, END, DURATION),
        ExecutionStatus.UNCONFIRMED: (None, None, None),
    }[status]
    return Execution(
        execution_id=execution_id,
        mission_id=mission_id,
        status=status,
        actual_start=timing[0],
        actual_end=timing[1],
        actual_duration=timing[2],
    )


@pytest.mark.parametrize(
    ("source_status", "destination_status"),
    [
        (ExecutionStatus.NOT_STARTED, ExecutionStatus.IN_PROGRESS),
        (ExecutionStatus.NOT_STARTED, ExecutionStatus.UNCONFIRMED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.COMPLETED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.INTERRUPTED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.UNCONFIRMED),
    ],
)
def test_allowed_execution_transitions(source_status, destination_status):
    source = execution(source_status)
    destination = execution(destination_status)

    validated = validate_execution_transition(source, destination)

    assert validated is destination


@pytest.mark.parametrize(
    "destination_status",
    [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED],
)
def test_not_started_rejects_direct_closed_transition(destination_status):
    with pytest.raises(
        ExecutionTransitionError,
        match="execution_transition_not_allowed",
    ):
        validate_execution_transition(
            execution(ExecutionStatus.NOT_STARTED),
            execution(destination_status),
        )


@pytest.mark.parametrize(
    "source_status",
    [
        ExecutionStatus.COMPLETED,
        ExecutionStatus.INTERRUPTED,
        ExecutionStatus.UNCONFIRMED,
    ],
)
@pytest.mark.parametrize("destination_status", list(ExecutionStatus))
def test_terminal_statuses_reject_every_outgoing_transition(
    source_status,
    destination_status,
):
    with pytest.raises(
        ExecutionTransitionError,
        match="execution_transition_not_allowed",
    ):
        validate_execution_transition(
            execution(source_status),
            execution(destination_status),
        )


@pytest.mark.parametrize(
    "status",
    [ExecutionStatus.NOT_STARTED, ExecutionStatus.IN_PROGRESS],
)
def test_non_terminal_same_state_transition_is_rejected(status):
    with pytest.raises(
        ExecutionTransitionError,
        match="execution_transition_not_allowed",
    ):
        validate_execution_transition(execution(status), execution(status))


@pytest.mark.parametrize(
    ("execution_id", "mission_id"),
    [("execution-2", "mission-1"), ("execution-1", "mission-2")],
)
def test_transition_rejects_identity_changes(execution_id, mission_id):
    with pytest.raises(
        ExecutionTransitionError,
        match="execution_transition_identity_mismatch",
    ):
        validate_execution_transition(
            execution(ExecutionStatus.NOT_STARTED),
            execution(
                ExecutionStatus.IN_PROGRESS,
                execution_id=execution_id,
                mission_id=mission_id,
            ),
        )


def test_transition_does_not_invent_or_modify_timing():
    source = execution(ExecutionStatus.NOT_STARTED)
    destination = execution(ExecutionStatus.IN_PROGRESS)

    validated = validate_execution_transition(source, destination)

    assert validated is destination
    assert validated.actual_start is START
    assert validated.actual_end is None
    assert validated.actual_duration is None
    assert source.actual_start is None


def test_invalid_destination_cannot_be_repaired_by_transition_layer():
    with pytest.raises(ValueError, match="in_progress_requires_start_only"):
        destination = Execution(
            execution_id="execution-1",
            mission_id="mission-1",
            status=ExecutionStatus.IN_PROGRESS,
            actual_start=None,
            actual_end=None,
            actual_duration=None,
        )
        validate_execution_transition(
            execution(ExecutionStatus.NOT_STARTED),
            destination,
        )


def test_transition_does_not_mutate_source_or_destination():
    source = execution(ExecutionStatus.NOT_STARTED)
    destination = execution(ExecutionStatus.IN_PROGRESS)

    validate_execution_transition(source, destination)

    with pytest.raises(FrozenInstanceError):
        source.status = ExecutionStatus.IN_PROGRESS
    with pytest.raises(FrozenInstanceError):
        destination.status = ExecutionStatus.COMPLETED


def test_unconfirmed_remains_distinct_and_failed_is_not_introduced():
    unconfirmed = execution(ExecutionStatus.UNCONFIRMED)
    not_started = execution(ExecutionStatus.NOT_STARTED)

    assert unconfirmed.status is not not_started.status
    assert "FAILED" not in ExecutionStatus.__members__
