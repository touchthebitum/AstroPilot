from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from decision.field_observation import (
    CloudCondition,
    FieldObservation,
    SeeingCondition,
    Transparency,
)


OBSERVED_AT = datetime(
    2026,
    9,
    1,
    21,
    17,
    30,
    123456,
    tzinfo=timezone.utc,
)


def observation(**overrides):
    values = {
        "observation_id": "observation-123",
        "execution_id": "execution-123",
        "observed_at_utc": OBSERVED_AT,
        "cloud_condition": CloudCondition.CLEAR,
        "transparency": None,
        "seeing": None,
        "dew_detected": None,
    }
    values.update(overrides)
    return FieldObservation(**values)


def test_field_observation_is_immutable():
    source = observation()

    with pytest.raises(FrozenInstanceError):
        source.dew_detected = True


def test_field_observation_enums_are_exact_string_enums():
    assert {item.value for item in CloudCondition} == {
        "clear",
        "few",
        "partly_cloudy",
        "mostly_cloudy",
        "overcast",
    }
    assert {item.value for item in Transparency} == {
        "excellent",
        "good",
        "fair",
        "poor",
    }
    assert {item.value for item in SeeingCondition} == {
        "excellent",
        "good",
        "fair",
        "poor",
    }
    assert all(isinstance(item, str) for item in CloudCondition)
    assert all(isinstance(item, str) for item in Transparency)
    assert all(isinstance(item, str) for item in SeeingCondition)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("observation_id", "", "invalid_observation_id"),
        ("observation_id", "../escape", "invalid_observation_id"),
        ("observation_id", "nested/path", "invalid_observation_id"),
        ("observation_id", ".hidden", "invalid_observation_id"),
        ("execution_id", "", "invalid_execution_id"),
        ("execution_id", "../escape", "invalid_execution_id"),
        ("execution_id", "nested/path", "invalid_execution_id"),
        ("execution_id", ".hidden", "invalid_execution_id"),
    ],
)
def test_field_observation_rejects_unsafe_identities(field, value, code):
    with pytest.raises(ValueError, match=code):
        observation(**{field: value})


def test_naive_observation_time_is_rejected():
    with pytest.raises(ValueError, match="invalid_observed_at_utc"):
        observation(observed_at_utc=datetime(2026, 9, 1, 21))


def test_observation_time_is_really_converted_to_utc_losslessly():
    offset = timezone(timedelta(hours=2))
    source = observation(observed_at_utc=OBSERVED_AT.astimezone(offset))

    assert source.observed_at_utc == OBSERVED_AT
    assert source.observed_at_utc.tzinfo is timezone.utc
    assert source.observed_at_utc.microsecond == 123456


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cloud_condition", "clear"),
        ("cloud_condition", Transparency.GOOD),
        ("transparency", "good"),
        ("transparency", SeeingCondition.GOOD),
        ("seeing", "fair"),
        ("seeing", Transparency.FAIR),
    ],
)
def test_categorical_values_are_strictly_typed(field, value):
    with pytest.raises(ValueError, match=f"invalid_{field}"):
        observation(**{field: value})


@pytest.mark.parametrize("dew_detected", [True, False, None])
def test_dew_detected_supports_explicit_tristate(dew_detected):
    source = observation(
        cloud_condition=(
            CloudCondition.CLEAR if dew_detected is None else None
        ),
        dew_detected=dew_detected,
    )

    if dew_detected is None:
        assert source.dew_detected is None
    else:
        assert source.dew_detected is dew_detected


@pytest.mark.parametrize("dew_detected", [0, 1, "false", object()])
def test_dew_detected_rejects_non_boolean_values(dew_detected):
    with pytest.raises(ValueError, match="invalid_dew_detected"):
        observation(dew_detected=dew_detected)


def test_explicit_false_counts_as_observed_field_data():
    source = observation(
        cloud_condition=None,
        transparency=None,
        seeing=None,
        dew_detected=False,
    )

    assert source.dew_detected is False


def test_at_least_one_field_value_is_required():
    with pytest.raises(ValueError, match="field_observation_value_required"):
        observation(
            cloud_condition=None,
            transparency=None,
            seeing=None,
            dew_detected=None,
        )


def test_observation_time_has_no_implicit_execution_window_constraint():
    far_from_any_execution_window = datetime(
        2035,
        1,
        1,
        12,
        0,
        tzinfo=timezone.utc,
    )

    source = observation(observed_at_utc=far_from_any_execution_window)

    assert source.observed_at_utc == far_from_any_execution_window
