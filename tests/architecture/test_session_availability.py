from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone

import pytest

from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)


START = datetime(2026, 9, 12, 22, 30, tzinfo=timezone(timedelta(hours=2)))
END = datetime(2026, 9, 13, 1, 15, tzinfo=timezone(timedelta(hours=2)))
DURATION = timedelta(hours=3)


def test_session_availability_modes_are_exact_and_contract_is_immutable():
    assert [(mode.name, mode.value) for mode in SessionAvailabilityMode] == [
        ("ALL_NIGHT", "all_night"),
        ("DURATION", "duration"),
        ("START_AND_DURATION", "start_and_duration"),
        ("UNTIL", "until"),
        ("FIXED_WINDOW", "fixed_window"),
    ]
    availability = SessionAvailability(mode=SessionAvailabilityMode.ALL_NIGHT)
    assert [field.name for field in fields(availability)] == [
        "mode", "start", "end", "duration",
    ]
    assert availability.start is availability.end is availability.duration is None
    with pytest.raises(FrozenInstanceError):
        availability.mode = SessionAvailabilityMode.DURATION


def test_each_mode_preserves_only_its_explicit_maximum_constraints():
    duration = SessionAvailability(
        mode=SessionAvailabilityMode.DURATION,
        duration=DURATION,
    )
    start_and_duration = SessionAvailability(
        mode=SessionAvailabilityMode.START_AND_DURATION,
        start=START,
        duration=DURATION,
    )
    until = SessionAvailability(
        mode=SessionAvailabilityMode.UNTIL,
        end=END,
    )
    fixed = SessionAvailability(
        mode=SessionAvailabilityMode.FIXED_WINDOW,
        start=START,
        end=END,
    )

    assert duration.start is duration.end is None
    assert duration.duration is DURATION
    assert start_and_duration.start is START
    assert start_and_duration.end is None
    assert start_and_duration.duration is DURATION
    assert until.start is until.duration is None
    assert until.end is END
    assert fixed.start is START
    assert fixed.end is END
    assert fixed.duration is None
    assert fixed.end > fixed.start


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "duration", "duration": DURATION},
        {"mode": SessionAvailabilityMode.ALL_NIGHT, "start": START},
        {"mode": SessionAvailabilityMode.ALL_NIGHT, "end": END},
        {"mode": SessionAvailabilityMode.ALL_NIGHT, "duration": DURATION},
        {"mode": SessionAvailabilityMode.DURATION},
        {"mode": SessionAvailabilityMode.DURATION, "duration": timedelta(0)},
        {"mode": SessionAvailabilityMode.DURATION, "duration": -DURATION},
        {"mode": SessionAvailabilityMode.DURATION, "duration": DURATION, "start": START},
        {"mode": SessionAvailabilityMode.DURATION, "duration": DURATION, "end": END},
        {"mode": SessionAvailabilityMode.START_AND_DURATION, "start": START},
        {"mode": SessionAvailabilityMode.START_AND_DURATION, "duration": DURATION},
        {
            "mode": SessionAvailabilityMode.START_AND_DURATION,
            "start": START,
            "end": END,
            "duration": DURATION,
        },
        {"mode": SessionAvailabilityMode.UNTIL},
        {"mode": SessionAvailabilityMode.UNTIL, "start": START, "end": END},
        {"mode": SessionAvailabilityMode.UNTIL, "end": END, "duration": DURATION},
        {"mode": SessionAvailabilityMode.FIXED_WINDOW, "start": START},
        {"mode": SessionAvailabilityMode.FIXED_WINDOW, "end": END},
        {
            "mode": SessionAvailabilityMode.FIXED_WINDOW,
            "start": START,
            "end": END,
            "duration": DURATION,
        },
        {
            "mode": SessionAvailabilityMode.FIXED_WINDOW,
            "start": END,
            "end": START,
        },
        {
            "mode": SessionAvailabilityMode.FIXED_WINDOW,
            "start": START,
            "end": START,
        },
    ],
)
def test_invalid_mode_field_combinations_fail_closed(kwargs):
    with pytest.raises((TypeError, ValueError)):
        SessionAvailability(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "mode": SessionAvailabilityMode.START_AND_DURATION,
            "start": START.replace(tzinfo=None),
            "duration": DURATION,
        },
        {
            "mode": SessionAvailabilityMode.UNTIL,
            "end": END.replace(tzinfo=None),
        },
        {
            "mode": SessionAvailabilityMode.FIXED_WINDOW,
            "start": START.replace(tzinfo=None),
            "end": END,
        },
        {
            "mode": SessionAvailabilityMode.FIXED_WINDOW,
            "start": START,
            "end": END.replace(tzinfo=None),
        },
    ],
)
def test_absolute_times_must_be_timezone_aware_datetimes(kwargs):
    with pytest.raises((TypeError, ValueError)):
        SessionAvailability(**kwargs)


@pytest.mark.parametrize("duration", [1, 3.0, "PT3H", None])
def test_duration_modes_require_a_real_positive_timedelta(duration):
    with pytest.raises((TypeError, ValueError)):
        SessionAvailability(
            mode=SessionAvailabilityMode.DURATION,
            duration=duration,
        )
