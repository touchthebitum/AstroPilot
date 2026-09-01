from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from decision.execution_record import ExecutionRecord


START = datetime(2026, 9, 1, 20, 15, 30, 123456, tzinfo=timezone.utc)


def execution(**overrides):
    values = {
        "execution_id": "execution-123",
        "decision_id": "decision-123",
        "started_at_utc": START,
        "ended_at_utc": START + timedelta(hours=2),
        "object": "M31",
        "hours": 1.5,
        "filter_type": "Ha",
    }
    values.update(overrides)
    return ExecutionRecord(**values)


def test_execution_record_is_immutable():
    record = execution()

    with pytest.raises(FrozenInstanceError):
        record.hours = 2.0


def test_execution_record_normalizes_aware_timestamps_to_utc_losslessly():
    offset = timezone(timedelta(hours=2))
    record = execution(
        started_at_utc=START.astimezone(offset),
        ended_at_utc=(START + timedelta(hours=2)).astimezone(offset),
    )

    assert record.started_at_utc == START
    assert record.started_at_utc.tzinfo is timezone.utc
    assert record.ended_at_utc == START + timedelta(hours=2)
    assert record.ended_at_utc.tzinfo is timezone.utc


@pytest.mark.parametrize("field", ["started_at_utc", "ended_at_utc"])
def test_execution_record_rejects_naive_timestamps(field):
    with pytest.raises(ValueError, match=f"invalid_{field}"):
        execution(**{field: datetime(2026, 9, 1, 20)})


@pytest.mark.parametrize(
    "ended_at",
    [START, START - timedelta(microseconds=1)],
)
def test_execution_record_requires_end_after_start(ended_at):
    with pytest.raises(ValueError, match="invalid_execution_time_range"):
        execution(ended_at_utc=ended_at)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("execution_id", "", "invalid_execution_id"),
        ("execution_id", "../escape", "invalid_execution_id"),
        ("execution_id", "nested/path", "invalid_execution_id"),
        ("decision_id", "", "invalid_decision_id"),
        ("decision_id", ".hidden", "invalid_decision_id"),
        ("object", "", "invalid_object"),
        ("object", "   ", "invalid_object"),
        ("filter_type", "", "invalid_filter_type"),
        ("filter_type", "  ", "invalid_filter_type"),
    ],
)
def test_execution_record_rejects_invalid_identity_or_text_fields(
    field,
    value,
    code,
):
    with pytest.raises(ValueError, match=code):
        execution(**{field: value})


@pytest.mark.parametrize(
    "hours",
    [True, False, 0, -1, float("nan"), float("inf"), float("-inf"), "1.5"],
)
def test_execution_record_rejects_invalid_hours(hours):
    with pytest.raises(ValueError, match="invalid_hours"):
        execution(hours=hours)


def test_hours_are_independent_from_wall_clock_duration():
    record = execution(
        ended_at_utc=START + timedelta(hours=4),
        hours=1.25,
    )

    assert record.hours == 1.25
    assert record.ended_at_utc - record.started_at_utc == timedelta(hours=4)


def test_manual_execution_and_missing_filter_are_supported():
    record = execution(decision_id=None, filter_type=None)

    assert record.decision_id is None
    assert record.filter_type is None
