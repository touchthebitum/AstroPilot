from dataclasses import FrozenInstanceError, MISSING, fields
from datetime import datetime, timedelta, timezone

import pytest

from decision.models.execution import Execution, ExecutionStatus


START = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
END = datetime(2026, 9, 11, 1, tzinfo=timezone.utc)
DURATION = timedelta(hours=3)


def execution(
    status,
    *,
    actual_start=None,
    actual_end=None,
    actual_duration=None,
    execution_id="execution-1",
    mission_id="mission-1",
):
    return Execution(
        execution_id=execution_id,
        mission_id=mission_id,
        status=status,
        actual_start=actual_start,
        actual_end=actual_end,
        actual_duration=actual_duration,
    )


@pytest.mark.parametrize(
    ("status", "actual_start", "actual_end", "actual_duration"),
    [
        (ExecutionStatus.NOT_STARTED, None, None, None),
        (ExecutionStatus.IN_PROGRESS, START, None, None),
        (ExecutionStatus.COMPLETED, START, END, DURATION),
        (ExecutionStatus.INTERRUPTED, START, END, DURATION),
        (ExecutionStatus.UNCONFIRMED, None, None, None),
    ],
)
def test_valid_execution_contracts(
    status,
    actual_start,
    actual_end,
    actual_duration,
):
    result = execution(
        status,
        actual_start=actual_start,
        actual_end=actual_end,
        actual_duration=actual_duration,
    )

    assert result.status is status
    assert result.actual_start is actual_start
    assert result.actual_end is actual_end
    assert result.actual_duration is actual_duration


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("execution_id", ""),
        ("execution_id", "   "),
        ("mission_id", ""),
        ("mission_id", "   "),
    ],
)
def test_execution_rejects_empty_identifiers(field_name, value):
    values = {field_name: value}

    with pytest.raises(ValueError, match=f"{field_name}_required"):
        execution(ExecutionStatus.NOT_STARTED, **values)


@pytest.mark.parametrize(
    ("status", "actual_start", "actual_end", "actual_duration"),
    [
        (ExecutionStatus.IN_PROGRESS, START.replace(tzinfo=None), None, None),
        (
            ExecutionStatus.COMPLETED,
            START.replace(tzinfo=None),
            END,
            DURATION,
        ),
        (
            ExecutionStatus.INTERRUPTED,
            START,
            END.replace(tzinfo=None),
            DURATION,
        ),
    ],
)
def test_execution_rejects_timezone_naive_actual_timestamps(
    status,
    actual_start,
    actual_end,
    actual_duration,
):
    with pytest.raises(ValueError, match="execution_timestamp_timezone_required"):
        execution(
            status,
            actual_start=actual_start,
            actual_end=actual_end,
            actual_duration=actual_duration,
        )


def test_not_started_rejects_timing():
    with pytest.raises(ValueError, match="not_started_requires_no_timing"):
        execution(ExecutionStatus.NOT_STARTED, actual_start=START)


def test_in_progress_requires_start():
    with pytest.raises(ValueError, match="in_progress_requires_start_only"):
        execution(ExecutionStatus.IN_PROGRESS)


@pytest.mark.parametrize(
    ("actual_end", "actual_duration"),
    [(END, None), (None, DURATION), (END, DURATION)],
)
def test_in_progress_rejects_end_or_duration(actual_end, actual_duration):
    with pytest.raises(ValueError, match="in_progress_requires_start_only"):
        execution(
            ExecutionStatus.IN_PROGRESS,
            actual_start=START,
            actual_end=actual_end,
            actual_duration=actual_duration,
        )


@pytest.mark.parametrize(
    "status",
    [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED],
)
def test_closed_execution_rejects_end_before_start(status):
    with pytest.raises(ValueError, match="execution_end_precedes_start"):
        execution(
            status,
            actual_start=END,
            actual_end=START,
            actual_duration=DURATION,
        )


@pytest.mark.parametrize(
    "status",
    [ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED],
)
def test_closed_execution_rejects_duration_mismatch(status):
    with pytest.raises(ValueError, match="execution_duration_mismatch"):
        execution(
            status,
            actual_start=START,
            actual_end=END,
            actual_duration=timedelta(hours=2),
        )


def test_closed_execution_requires_explicit_non_negative_duration():
    with pytest.raises(ValueError, match="closed_execution_requires_timing"):
        execution(
            ExecutionStatus.COMPLETED,
            actual_start=START,
            actual_end=END,
        )

    with pytest.raises(ValueError, match="execution_duration_must_be_non_negative"):
        execution(
            ExecutionStatus.COMPLETED,
            actual_start=START,
            actual_end=END,
            actual_duration=timedelta(seconds=-1),
        )


@pytest.mark.parametrize(
    ("actual_start", "actual_end", "actual_duration"),
    [(START, None, None), (None, END, None), (None, None, DURATION)],
)
def test_unconfirmed_rejects_inferred_or_supplied_timing(
    actual_start,
    actual_end,
    actual_duration,
):
    with pytest.raises(ValueError, match="unconfirmed_requires_no_timing"):
        execution(
            ExecutionStatus.UNCONFIRMED,
            actual_start=actual_start,
            actual_end=actual_end,
            actual_duration=actual_duration,
        )


def test_unconfirmed_remains_distinct_from_not_started():
    unconfirmed = execution(ExecutionStatus.UNCONFIRMED)
    not_started = execution(ExecutionStatus.NOT_STARTED)

    assert unconfirmed.status is ExecutionStatus.UNCONFIRMED
    assert not_started.status is ExecutionStatus.NOT_STARTED
    assert unconfirmed != not_started


def test_execution_is_immutable_and_does_not_mutate_mission_identity():
    result = execution(ExecutionStatus.IN_PROGRESS, actual_start=START)

    with pytest.raises(FrozenInstanceError):
        result.status = ExecutionStatus.COMPLETED
    with pytest.raises(FrozenInstanceError):
        result.mission_id = "mission-2"


def test_execution_status_has_no_failed_member():
    assert set(ExecutionStatus.__members__) == {
        "NOT_STARTED",
        "IN_PROGRESS",
        "COMPLETED",
        "INTERRUPTED",
        "UNCONFIRMED",
    }


def test_execution_has_exact_fields_and_no_hidden_defaults():
    contract_fields = fields(Execution)

    assert tuple(field.name for field in contract_fields) == (
        "execution_id",
        "mission_id",
        "status",
        "actual_start",
        "actual_end",
        "actual_duration",
    )
    assert all(field.default is MISSING for field in contract_fields)
    assert all(field.default_factory is MISSING for field in contract_fields)
