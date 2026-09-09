from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)


START = datetime(2026, 9, 12, 22, 30, tzinfo=timezone(timedelta(hours=2)))


def assessment(*, hours, scores):
    timeline = [
        SimpleNamespace(
            start_hour=index * hours / len(scores),
            end_hour=(index + 1) * hours / len(scores),
            productivity_score=score,
        )
        for index, score in enumerate(scores)
    ] if scores else []
    return ProductiveWindowAssessment(
        window_start=START,
        window_end=START + timedelta(hours=hours),
        recommended_hours=hours,
        expected_gain=8.0,
        productivity=SimpleNamespace(timeline=timeline),
    )


def test_duration_preserves_an_existing_window_within_capacity():
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=2, scores=[])
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.DURATION,
        duration=timedelta(hours=3),
    )

    window = select_duration_availability_window(source, availability)

    assert [field.name for field in fields(window)] == ["window_start", "window_end"]
    assert window.window_start is source.window_start
    assert window.window_end is source.window_end
    assert source.recommended_hours == 2
    assert source.expected_gain == 8.0
    with pytest.raises(FrozenInstanceError):
        window.window_end = START


def test_duration_selects_unique_best_continuous_window_from_existing_productivity():
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=4, scores=[0.1, 0.2, 0.9, 0.8])
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.DURATION,
        duration=timedelta(hours=2),
    )

    window = select_duration_availability_window(source, availability)

    assert window.window_start == START + timedelta(hours=2)
    assert window.window_end == START + timedelta(hours=4)
    assert window.window_end - window.window_start <= availability.duration
    assert window.window_start >= source.window_start
    assert window.window_end <= source.window_end


def test_duration_can_select_at_a_slice_boundary_for_fractional_capacity():
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=4, scores=[0.1, 0.9, 0.8, 0.1])
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.DURATION,
        duration=timedelta(hours=1, minutes=30),
    )

    window = select_duration_availability_window(source, availability)

    assert window.window_start == START + timedelta(hours=1)
    assert window.window_end == START + timedelta(hours=2, minutes=30)


def test_start_and_duration_preserves_productive_window_fully_inside_availability():
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=2, scores=[0.1, 0.9])
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.START_AND_DURATION,
        start=START - timedelta(hours=1),
        duration=timedelta(hours=4),
    )

    window = select_duration_availability_window(source, availability)

    assert window.window_start is source.window_start
    assert window.window_end is source.window_end


@pytest.mark.parametrize(
    ("availability_start", "duration", "expected_start", "expected_end"),
    [
        (
            START + timedelta(hours=1),
            timedelta(hours=4),
            START + timedelta(hours=1),
            START + timedelta(hours=4),
        ),
        (
            START - timedelta(hours=1),
            timedelta(hours=3),
            START,
            START + timedelta(hours=2),
        ),
        (
            START + timedelta(hours=1),
            timedelta(hours=2),
            START + timedelta(hours=1),
            START + timedelta(hours=3),
        ),
    ],
)
def test_start_and_duration_returns_only_exact_productive_overlap(
    availability_start,
    duration,
    expected_start,
    expected_end,
):
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=4, scores=[0.9, 0.1, 0.1, 0.9])
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.START_AND_DURATION,
        start=availability_start,
        duration=duration,
    )

    window = select_duration_availability_window(source, availability)

    assert window.window_start == expected_start
    assert window.window_end == expected_end
    assert window.window_end - window.window_start <= availability.duration


@pytest.mark.parametrize(
    "availability",
    [
        SessionAvailability(
            mode=SessionAvailabilityMode.START_AND_DURATION,
            start=START - timedelta(hours=3),
            duration=timedelta(hours=2),
        ),
        SessionAvailability(
            mode=SessionAvailabilityMode.START_AND_DURATION,
            start=START + timedelta(hours=5),
            duration=timedelta(hours=2),
        ),
    ],
)
def test_start_and_duration_returns_none_without_productive_overlap(availability):
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    assert select_duration_availability_window(
        assessment(hours=4, scores=[0.1, 0.9, 0.8, 0.1]),
        availability,
    ) is None


@pytest.mark.parametrize("offset_hours", [4, 6])
def test_until_preserves_productive_window_when_limit_reaches_or_follows_end(
    offset_hours,
):
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=4, scores=[0.1, 0.9, 0.8, 0.1])
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.UNTIL,
        end=START + timedelta(hours=offset_hours),
    )

    window = select_duration_availability_window(source, availability)

    assert window.window_start is source.window_start
    assert window.window_end is source.window_end


def test_until_truncates_only_productive_window_end_at_explicit_limit():
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=4, scores=[0.9, 0.1, 0.1, 0.9])
    until = START + timedelta(hours=2, minutes=15)
    availability = SessionAvailability(
        mode=SessionAvailabilityMode.UNTIL,
        end=until,
    )

    window = select_duration_availability_window(source, availability)

    assert window.window_start is source.window_start
    assert window.window_end is until
    assert window.window_end.date() > window.window_start.date()


@pytest.mark.parametrize("offset_hours", [-1, 0])
def test_until_returns_none_when_limit_precedes_or_equals_productive_start(
    offset_hours,
):
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    assert select_duration_availability_window(
        assessment(hours=4, scores=[0.1, 0.9, 0.8, 0.1]),
        SessionAvailability(
            mode=SessionAvailabilityMode.UNTIL,
            end=START + timedelta(hours=offset_hours),
        ),
    ) is None


@pytest.mark.parametrize(
    "availability",
    [
        SessionAvailability(mode=SessionAvailabilityMode.ALL_NIGHT),
        SessionAvailability(
            mode=SessionAvailabilityMode.FIXED_WINDOW,
            start=START,
            end=START + timedelta(hours=2),
        ),
    ],
)
def test_other_availability_modes_remain_inactive(availability):
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    with pytest.raises(ValueError, match="session_availability_mode_inactive"):
        select_duration_availability_window(
            assessment(hours=2, scores=[0.5, 0.6]),
            availability,
        )


def test_duration_fails_closed_when_temporal_evidence_is_incomplete():
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    source = assessment(hours=4, scores=[0.1, 0.8, 0.9, 0.2])
    source.productivity.timeline[1].start_hour = 1.5

    with pytest.raises(ValueError, match="duration_window_temporal_evidence_required"):
        select_duration_availability_window(
            source,
            SessionAvailability(
                mode=SessionAvailabilityMode.DURATION,
                duration=timedelta(hours=2),
            ),
        )


def test_duration_fails_closed_when_best_window_is_not_unique():
    from decision.services.session_availability_windowing import (
        select_duration_availability_window,
    )

    with pytest.raises(ValueError, match="ambiguous_best_duration_window"):
        select_duration_availability_window(
            assessment(hours=4, scores=[0.8, 0.8, 0.8, 0.8]),
            SessionAvailability(
                mode=SessionAvailabilityMode.DURATION,
                duration=timedelta(hours=2),
            ),
        )
