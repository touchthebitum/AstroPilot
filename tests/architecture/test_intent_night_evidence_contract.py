from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone

import pytest

from decision.models.intent_night_evidence import IntentNightEvidence


START = datetime(2024, 10, 15, 20, 0, tzinfo=timezone.utc)
END = datetime(2024, 10, 15, 22, 0, tzinfo=timezone.utc)
MIDPOINT = datetime(2024, 10, 15, 21, 0, tzinfo=timezone.utc)


def _evidence(**overrides) -> IntentNightEvidence:
    values = {
        "imaging_field_id": "sh2-129_ou4",
        "actionable_window_start": START,
        "actionable_window_end": END,
        "actionable_duration_hours": 2.0,
        "reference_time": MIDPOINT,
        "moon_illumination": 0.75,
        "moon_altitude_deg": 30.0,
        "moon_separation_deg": 60.0,
    }
    values.update(overrides)
    return IntentNightEvidence(**values)


def test_complete_evidence_is_minimal_immutable_and_preserves_identity():
    evidence = _evidence(imaging_field_id=" sh2-129_ou4 ")

    assert tuple(field.name for field in fields(evidence)) == (
        "imaging_field_id",
        "actionable_window_start",
        "actionable_window_end",
        "actionable_duration_hours",
        "reference_time",
        "moon_illumination",
        "moon_altitude_deg",
        "moon_separation_deg",
    )
    assert evidence.imaging_field_id == " sh2-129_ou4 "
    assert evidence.moon_illumination == 0.75
    with pytest.raises((FrozenInstanceError, AttributeError)):
        evidence.moon_illumination = None


@pytest.mark.parametrize("imaging_field_id", ["", "   ", 42, None])
def test_rejects_empty_or_non_string_imaging_field_id(imaging_field_id):
    with pytest.raises(ValueError, match="imaging_field_id"):
        _evidence(imaging_field_id=imaging_field_id)


@pytest.mark.parametrize(
    "field_name",
    ["actionable_window_start", "actionable_window_end", "reference_time"],
)
def test_rejects_naive_datetimes(field_name):
    with pytest.raises(ValueError, match="timezone-aware"):
        _evidence(**{field_name: datetime(2024, 10, 15, 21, 0)})


@pytest.mark.parametrize("end", [START, START - timedelta(microseconds=1)])
def test_rejects_non_positive_window(end):
    with pytest.raises(ValueError, match="must be after"):
        _evidence(actionable_window_end=end)


@pytest.mark.parametrize(
    "duration",
    [True, False, "2.0", None, float("nan"), float("inf"), 0.0, -1.0, 2.1],
)
def test_rejects_invalid_or_incoherent_duration(duration):
    with pytest.raises(ValueError, match="actionable_duration_hours"):
        _evidence(actionable_duration_hours=duration)


def test_duration_tolerance_is_small_and_deterministic():
    assert _evidence(actionable_duration_hours=2.0 + 0.5e-9)
    with pytest.raises(ValueError, match="actionable_duration_hours"):
        _evidence(actionable_duration_hours=2.0 + 1.1e-9)


@pytest.mark.parametrize(
    "reference_time",
    [START - timedelta(microseconds=1), END + timedelta(microseconds=1)],
)
def test_rejects_reference_time_outside_window(reference_time):
    with pytest.raises(ValueError, match="reference_time"):
        _evidence(reference_time=reference_time)


@pytest.mark.parametrize(
    ("field_name", "valid_values"),
    [
        ("moon_illumination", [None, 0.0, 1.0]),
        ("moon_altitude_deg", [None, -90.0, 90.0]),
        ("moon_separation_deg", [None, 0.0, 180.0]),
    ],
)
def test_accepts_optional_moon_values_and_exact_bounds(
    field_name,
    valid_values,
):
    for value in valid_values:
        assert getattr(_evidence(**{field_name: value}), field_name) == value


@pytest.mark.parametrize(
    ("field_name", "invalid_values"),
    [
        (
            "moon_illumination",
            [True, "0.5", float("nan"), float("inf"), -0.01, 1.01],
        ),
        (
            "moon_altitude_deg",
            [False, "0", float("nan"), float("-inf"), -90.01, 90.01],
        ),
        (
            "moon_separation_deg",
            [True, "60", float("nan"), float("inf"), -0.01, 180.01],
        ),
    ],
)
def test_rejects_invalid_moon_values(field_name, invalid_values):
    for value in invalid_values:
        with pytest.raises(ValueError, match=field_name):
            _evidence(**{field_name: value})
