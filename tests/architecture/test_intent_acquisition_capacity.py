"""Contract: Tonight duration and gain share the selected intent's capacity."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import astro_score
from decision.mission.mission_assembler import ProductiveWindowAssessment, _mission_timing_assessment
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.portfolio.project_state import project_remaining_hours
from decision.portfolio.project_gain import session_portfolio_gain

START = datetime(2026, 10, 6, 20, tzinfo=timezone.utc)


def project(*, acquired=0.5, legacy_remaining=0):
    return {
        "imaging_field_id": "sh2-129_ou4", "hours": 4 - legacy_remaining,
        "target_hours": 4,
        "acquisition_intent_targets": [
            {"acquisition_intent_id": "sh2-129_ha", "target_hours": 2},
            {"acquisition_intent_id": "ou4_oiii", "target_hours": 10},
        ],
        "acquisition_intent_progress": [
            {"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": acquired * 3600},
            {"acquisition_intent_id": "ou4_oiii", "acquired_duration_manual": 0},
        ],
    }


def mission_input(monkeypatch, value, *, selected="sh2-129_ha", profile_extra=None, **kwargs):
    monkeypatch.setattr(astro_score.FilterInventoryLoader, "load", lambda: [])
    evaluation = {
        "catalog_key": "Sh2-129", "remaining_hours": project_remaining_hours("Sh2-129", {"Sh2-129": value}),
        "window": {"start": START, "end": START + timedelta(hours=4)},
        "imaging_field_id": "sh2-129_ou4", "selected_acquisition_intent_id": selected,
    }
    return astro_score.build_mission_input(evaluation, profile={"projects": {"Sh2-129": value}, **(profile_extra or {})}, **kwargs)


def timing(value, *, duration=None, windows=None):
    assessment = ProductiveWindowAssessment(
        window_start=START, window_end=START + timedelta(hours=4),
        recommended_hours=value.recommended_hours, expected_gain=value.expected_gain,
        maximum_mission_hours=value.recommended_hours,
        acquisition_capacity=value.acquisition_capacity,
        productivity=SimpleNamespace(
            timeline=[SimpleNamespace(start_hour=0, end_hour=4, productivity_score=1)],
            windows=windows if windows is not None else [SimpleNamespace(
                start_hour=0, end_hour=4, productivity=1, productive=True)]),
    )
    availability = SessionAvailability(SessionAvailabilityMode.START_AND_DURATION, start=START, duration=timedelta(hours=duration)) if duration else None
    return _mission_timing_assessment(assessment, availability)[0]


@pytest.mark.parametrize("legacy_remaining", [0, 4])
def test_legacy_cannot_block_or_expand_modern_capacity(monkeypatch, legacy_remaining):
    result = mission_input(monkeypatch, project(legacy_remaining=legacy_remaining))
    assert result.acquisition_capacity.remaining_hours == 1.5
    assert result.recommended_hours == 1.5
    assert result.expected_gain == 75
    assert timing(result)[2:] == (1.5, 75)


@pytest.mark.parametrize("acquired", [1.5, 2, 3])
def test_short_or_completed_intent_never_overacquired(monkeypatch, acquired):
    result = mission_input(monkeypatch, project(acquired=acquired, legacy_remaining=4))
    assert result.recommended_hours == max(2 - acquired, 0)
    assert timing(result) is None


def test_unknown_progress_is_preserved_and_closed(monkeypatch):
    value = project(legacy_remaining=4)
    value["acquisition_intent_progress"] = value["acquisition_intent_progress"][1:]
    result = mission_input(monkeypatch, value)
    assert result.acquisition_capacity.remaining_hours is None
    assert result.recommended_hours == result.expected_gain == 0
    assert timing(result) is None


def test_selected_intent_only_and_user_duration_prorate_gain(monkeypatch):
    result = mission_input(monkeypatch, project(), selected="ou4_oiii")
    assert result.acquisition_capacity.remaining_hours == 10
    assert result.recommended_hours == 4
    assert result.expected_gain == 40
    assert timing(result, duration=1.25)[2:] == (1.25, 12.5)


def test_legacy_reads_and_profile_unchanged(monkeypatch):
    value = {"hours": 1, "target_hours": 4}
    before = deepcopy(value)
    result = mission_input(monkeypatch, value, selected=None)
    assert result.acquisition_capacity is None
    assert result.recommended_hours == 3
    assert result.expected_gain == session_portfolio_gain("Sh2-129", 3, projects={"Sh2-129": value})
    assert project_remaining_hours("Sh2-129", {"Sh2-129": value}) == 3
    assert value == before


def test_modern_without_selection_is_closed(monkeypatch):
    result = mission_input(monkeypatch, project(legacy_remaining=4), selected=None)
    assert result.recommended_hours == result.expected_gain == 0
    assert timing(result) is None


def test_preselection_uses_physical_window_not_legacy_capacity(monkeypatch):
    result = mission_input(monkeypatch, project(), selected=None, for_intent_selection=True)
    assert result.recommended_hours == 4
    assert result.expected_gain == 0


def test_disjoint_windows_are_not_added(monkeypatch):
    result = mission_input(monkeypatch, project())
    windows = [SimpleNamespace(start_hour=start, end_hour=start + 0.75, productivity=1, productive=True) for start in (0, 2)]
    assert timing(result, windows=windows) is None


def test_partial_progress_is_rejected_without_legacy_fallback(monkeypatch):
    value = project(legacy_remaining=4)
    value["acquisition_intent_progress"][0] = {"acquisition_intent_id": "sh2-129_ha", "acquired_frames": 2}
    with pytest.raises(ValueError, match="complete source"):
        mission_input(monkeypatch, value)


def test_preselection_cannot_authorize_mission(monkeypatch):
    from decision.mission.mission_assembler import MissionAssembler
    result = mission_input(monkeypatch, project(), selected=None, for_intent_selection=True)
    with pytest.raises(ValueError, match="preselection_evidence_cannot_authorize_mission"):
        MissionAssembler.build("Sh2-129", None, None, [], [], mission_input=result)


def test_unknown_modern_capacity_never_calls_future_legacy_fallback(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("unknown modern progress invoked legacy future fallback")
    monkeypatch.setattr(astro_score.future_engine, "estimate", unexpected)
    value = project(legacy_remaining=4)
    value.pop("acquisition_intent_progress")
    candidate = astro_score.recommend_project_for_night(
        [{"name": "Sh2-129", "catalog_key": "Sh2-129", "global_score": 75}],
        available_hours=2, profile={"projects": {"Sh2-129": value}},
    ).candidates[0]
    assert candidate.acquisition_intent_remaining_progress[0].remaining_hours is None


def test_identified_execution_credit_reduces_only_selected_capacity(monkeypatch):
    value = project()
    before = deepcopy(value)
    credits = {"execution-1": {
        "execution_id": "execution-1", "mission_id": "mission-1",
        "decision_id": "decision-1", "selection_id": "selection-1",
        "project_id": "Sh2-129", "imaging_field_id": "sh2-129_ou4",
        "acquisition_intent_id": "sh2-129_ha", "evidence_ids": ["evidence-1"],
        "usable_durations_us": [1_800_000_000], "total_duration_us": 1_800_000_000,
        "applied_at": "2026-10-06T19:00:00+00:00",
    }}
    result = mission_input(monkeypatch, value, profile_extra={"intent_progress_credits": credits})
    assert result.acquisition_capacity.remaining_hours == 1
    assert result.recommended_hours == 1
    assert result.expected_gain == 50
    assert value == before
    other = mission_input(monkeypatch, value, selected="ou4_oiii", profile_extra={"intent_progress_credits": credits})
    assert other.acquisition_capacity.remaining_hours == 10


def test_intent_identity_mismatch_is_rejected(monkeypatch):
    from dataclasses import replace
    result = mission_input(monkeypatch, project())
    with pytest.raises(ValueError, match="acquisition_capacity_intent_mismatch"):
        replace(result, acquisition_intent_id="ou4_oiii")
    with pytest.raises(ValueError, match="exceeds_acquisition_capacity"):
        replace(result, recommended_hours=2)


def test_unrelated_unknown_progress_does_not_override_selected_intent(monkeypatch):
    value = project()
    value["acquisition_intent_progress"] = value["acquisition_intent_progress"][:1]
    result = mission_input(monkeypatch, value)
    assert result.recommended_hours == 1.5
    assert result.expected_gain == 75
