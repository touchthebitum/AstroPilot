from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from decision.mission.mission_assembler import (
    ProductiveWindowAssessment,
    _mission_timing_for_availability,
)
from decision.models.session_availability import (
    SessionAvailability,
    SessionAvailabilityMode,
)
from decision.services.session_availability_windowing import (
    select_continuous_actionable_productive_window,
)


START = datetime(2026, 9, 20, 22, tzinfo=timezone.utc)


def assessment(
    scores,
    *,
    productive_windows=((0.0, 2.0),),
    recommended_hours=2.0,
    maximum_mission_hours=2.0,
    expected_gain=6.0,
):
    timeline = tuple(
        SimpleNamespace(
            start_hour=float(index),
            end_hour=float(index + 1),
            productivity_score=score,
        )
        for index, score in enumerate(scores)
    )
    windows = [
        SimpleNamespace(
            start_hour=start,
            end_hour=end,
            productivity=sum(
                slice_.productivity_score
                * max(
                    0.0,
                    min(end, slice_.end_hour) - max(start, slice_.start_hour),
                )
                for slice_ in timeline
            ) / (end - start),
            productive=True,
        )
        for start, end in productive_windows
    ]
    return ProductiveWindowAssessment(
        window_start=START,
        window_end=START + timedelta(hours=len(scores)),
        recommended_hours=recommended_hours,
        expected_gain=expected_gain,
        productivity=SimpleNamespace(
            windows=windows,
            timeline=timeline,
        ),
        maximum_mission_hours=maximum_mission_hours,
    )


@pytest.mark.parametrize(
    ("maximum_hours", "expected_hours"),
    ((2.0, 2.0), (1.0, 1.0), (1.5, 1.5)),
)
def test_project_cap_limits_the_real_mission_window(maximum_hours, expected_hours):
    timing = _mission_timing_for_availability(
        assessment([0.8, 0.8], maximum_mission_hours=maximum_hours),
        None,
    )

    assert timing[2] == expected_hours
    assert timing[1] - timing[0] == timedelta(hours=expected_hours)


def test_project_need_below_minimum_is_not_artificially_extended():
    source = assessment([0.8, 0.8], maximum_mission_hours=0.75)

    assert select_continuous_actionable_productive_window(source, None) is None
    assert _mission_timing_for_availability(source, None) is None


def test_availability_and_project_cap_apply_the_strictest_duration():
    source = assessment(
        [0.8, 0.85],
        recommended_hours=2.0,
        maximum_mission_hours=1.5,
        expected_gain=6.0,
    )
    availability = SessionAvailability(
        SessionAvailabilityMode.FIXED_WINDOW,
        start=START,
        end=START + timedelta(hours=1, minutes=15),
    )

    timing = _mission_timing_for_availability(source, availability)

    assert timing[2] == 1.25
    assert timing[3] == 3.75


def test_duration_selects_the_more_productive_final_hour():
    source = assessment([0.71, 0.95])
    availability = SessionAvailability(
        SessionAvailabilityMode.DURATION,
        duration=timedelta(hours=1),
    )

    selected = select_continuous_actionable_productive_window(
        source,
        availability,
    )

    assert selected.window_start == START + timedelta(hours=1)
    assert selected.window_end == START + timedelta(hours=2)


def test_duration_selects_a_unique_best_central_subwindow():
    source = assessment(
        [0.71, 0.95, 0.8],
        productive_windows=((0.0, 3.0),),
        maximum_mission_hours=3.0,
    )
    availability = SessionAvailability(
        SessionAvailabilityMode.DURATION,
        duration=timedelta(hours=1),
    )

    selected = select_continuous_actionable_productive_window(
        source,
        availability,
    )

    assert selected.window_start == START + timedelta(hours=1)
    assert selected.window_end == START + timedelta(hours=2)


def test_duration_tie_preserves_the_existing_fail_closed_contract():
    source = assessment([0.8, 0.8])

    with pytest.raises(ValueError, match="ambiguous_best_duration_window"):
        select_continuous_actionable_productive_window(
            source,
            SessionAvailability(
                SessionAvailabilityMode.DURATION,
                duration=timedelta(hours=1),
            ),
        )


@pytest.mark.parametrize(
    ("duration", "expected"),
    ((timedelta(minutes=59), None), (timedelta(hours=1), 1.0)),
)
def test_duration_respects_the_inclusive_sixty_minute_minimum(duration, expected):
    source = assessment([0.8, 0.9])

    selected = select_continuous_actionable_productive_window(
        source,
        SessionAvailability(SessionAvailabilityMode.DURATION, duration=duration),
    )

    if expected is None:
        assert selected is None
    else:
        assert selected.window_end - selected.window_start == timedelta(hours=expected)


def test_duration_longer_than_productive_window_uses_only_that_window():
    source = assessment(
        [0.2, 0.9, 0.9],
        productive_windows=((1.0, 3.0),),
        maximum_mission_hours=3.0,
    )

    selected = select_continuous_actionable_productive_window(
        source,
        SessionAvailability(
            SessionAvailabilityMode.DURATION,
            duration=timedelta(hours=4),
        ),
    )

    assert selected.window_start == START + timedelta(hours=1)
    assert selected.window_end == START + timedelta(hours=3)


def test_duration_never_concatenates_separated_short_windows():
    source = assessment(
        [0.9, 0.2, 0.95],
        productive_windows=((0.0, 0.75), (2.0, 2.75)),
        maximum_mission_hours=3.0,
    )

    assert select_continuous_actionable_productive_window(
        source,
        SessionAvailability(
            SessionAvailabilityMode.DURATION,
            duration=timedelta(hours=2),
        ),
    ) is None
