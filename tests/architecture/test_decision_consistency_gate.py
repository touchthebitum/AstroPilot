from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from decision.mission.night_mission import NightMission
from decision.validation.decision_consistency import (
    DecisionConsistencyError,
    DecisionConsistencyGate,
)


START = datetime(2026, 9, 1, 22, tzinfo=timezone.utc)


def mission(**overrides):
    window = SimpleNamespace(
        start_hour=0.0,
        end_hour=2.0,
        productivity=0.8,
        productive=True,
    )
    productivity = SimpleNamespace(
        astronomical_hours=3.0,
        productive_hours=2.0,
        confidence=2 / 3,
        windows=[window],
    )
    values = {
        "target": "M31",
        "confidence": 0.9,
        "window_start": START,
        "window_end": START + timedelta(hours=3),
        "recommended_hours": 2.0,
        "expected_gain": 4.0,
        "productivity": productivity,
    }
    values.update(overrides)
    return NightMission(**values)


def test_consistent_operational_mission_passes_the_gate():
    DecisionConsistencyGate.validate_mission(mission())


@pytest.mark.parametrize(
    ("change", "issue"),
    [
        ({"recommended_hours": float("nan")}, "invalid_recommended_hours"),
        ({"expected_gain": -1.0}, "expected_gain_below_minimum"),
        ({"window_end": START}, "window_not_forward"),
        ({"window_start": START.replace(tzinfo=None)}, "invalid_window_start"),
    ],
)
def test_invalid_top_level_values_are_rejected(change, issue):
    with pytest.raises(DecisionConsistencyError) as caught:
        DecisionConsistencyGate.validate_mission(mission(**change))

    assert issue in caught.value.issues


def test_productive_hours_cannot_exceed_the_astronomical_window():
    productivity = mission().productivity
    productivity.productive_hours = 3.5

    with pytest.raises(DecisionConsistencyError) as caught:
        DecisionConsistencyGate.validate_mission(mission(productivity=productivity))

    assert "productive_hours_exceed_astronomical_hours" in caught.value.issues


def test_recommended_hours_cannot_exceed_productive_capacity():
    with pytest.raises(DecisionConsistencyError) as caught:
        DecisionConsistencyGate.validate_mission(mission(recommended_hours=2.5))

    assert "recommended_hours_exceed_productive_hours" in caught.value.issues


def test_window_must_be_productive_forward_and_inside_the_night():
    productivity = mission().productivity
    productivity.windows = [
        SimpleNamespace(
            start_hour=2.5,
            end_hour=3.5,
            productivity=0.5,
            productive=False,
        )
    ]

    with pytest.raises(DecisionConsistencyError) as caught:
        DecisionConsistencyGate.validate_mission(mission(productivity=productivity))

    assert "window_0_outside_night" in caught.value.issues
    assert "window_0_not_productive" in caught.value.issues


def test_no_productive_window_is_a_business_state_not_corrupt_data():
    productivity = mission().productivity
    productivity.productive_hours = 0.9
    productivity.confidence = 0.3
    productivity.windows = []
    candidate = mission(
        productivity=productivity,
        recommended_hours=0.0,
        expected_gain=0.0,
    )

    DecisionConsistencyGate.validate_mission(candidate)
    assert DecisionConsistencyGate.has_productive_window(candidate) is False
