"""Missing commitment must preserve physical preview and forbid engagement."""
from datetime import timedelta

import pytest

from test_session_actionability_contract import assessment, candidate, START
from decision.mission.mission_assembler import _mission_timing_assessment
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.services.candidate_assessment import CandidateViabilityEvaluator, select_actionable_alternatives
from types import SimpleNamespace


def test_missing_availability_cannot_authorize_mission_timing():
    source = assessment([1.0] * 16, expected_gain=20)
    timing, refusal = _mission_timing_assessment(source, None)
    assert timing is None
    assert refusal.cause_code == "user_availability_required"
    assert refusal.best_productive_window_minutes is None
    assert refusal.productivity_breakdown is None
    assert CandidateViabilityEvaluator.is_viable(candidate(source))


@pytest.mark.parametrize('availability,hours', [
    (SessionAvailability(mode=SessionAvailabilityMode.ALL_NIGHT), 4),
    (SessionAvailability(mode=SessionAvailabilityMode.UNTIL, end=START + timedelta(hours=2)), 2),
    (SessionAvailability(mode=SessionAvailabilityMode.START_AND_DURATION, start=START + timedelta(hours=1), duration=timedelta(hours=2)), 2),
])
def test_explicit_availability_authorizes_only_bounded_time(availability, hours):
    source = assessment([1.0] * 16, expected_gain=20)
    timing, refusal = _mission_timing_assessment(source, availability)
    assert refusal is None
    assert timing[2] == hours
    assert timing[1] - timing[0] == timedelta(hours=hours)
    assert timing[3] <= 20
    assert _mission_timing_assessment(source, None)[0] is None


def test_no_actionable_alternatives_without_commitment():
    source = assessment([1.0] * 16)
    assert select_actionable_alternatives(
        [SimpleNamespace(catalog_key='M42')], {'M42'}, {'M42': candidate(source)},
        None, primary_catalog_key='M31',
    ) == ()


@pytest.mark.parametrize("minutes", [0, 30, 59, 60, 90, 120, 180, 240])
def test_restrictive_availability_and_missing_are_never_more_permissive(minutes):
    source = assessment([1.0] * 16, expected_gain=20)
    broad = SessionAvailability(mode=SessionAvailabilityMode.ALL_NIGHT)
    restricted = SessionAvailability(mode=SessionAvailabilityMode.UNTIL, end=START + timedelta(minutes=minutes))
    broad_timing, _ = _mission_timing_assessment(source, broad)
    timing, _ = _mission_timing_assessment(source, restricted)
    assert timing is None or (timing[2] <= broad_timing[2] and timing[3] <= broad_timing[3])
    assert _mission_timing_assessment(source, None)[0] is None


def test_named_physical_and_actionable_boundaries_preserve_missing_provenance():
    from decision.services.session_availability_windowing import (
        evaluate_physical_productive_window, evaluate_continuous_actionable_productive_window,
    )
    source = assessment([1.0] * 16)
    assert evaluate_physical_productive_window(source, None).window is not None
    authorized = evaluate_continuous_actionable_productive_window(source, None)
    assert authorized.window is None
    assert authorized.refusal.conclusion.value == "user_availability_required"
