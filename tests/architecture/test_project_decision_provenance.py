from copy import deepcopy
from types import SimpleNamespace

import pytest
import astro_score
from decision.definitions.production_imaging_fields import IMAGING_FIELD_DEFINITIONS

FIELD = IMAGING_FIELD_DEFINITIONS[0]

@pytest.mark.parametrize("removed", [
    ("imaging_field_id",), ("acquisition_intent_targets",),
    ("acquisition_intent_progress",),
    ("imaging_field_id", "acquisition_intent_targets", "acquisition_intent_progress"),
])
def test_erasing_provenance_never_promotes_project(monkeypatch, removed):
    monkeypatch.setattr(astro_score.future_engine, "estimate", lambda *a, **k:
                        SimpleNamespace(risk="FAIBLE", opportunity_ratio=1))
    project = {"hours": 2, "target_hours": 20, "importance": 5,
               "imaging_field_id": FIELD.imaging_field_id,
               "acquisition_intent_targets": [
                   {"acquisition_intent_id": "sh2-129_ha", "target_hours": 2}],
               "acquisition_intent_progress": []}
    objects = [{"name": key, "catalog_key": key, "global_score": score}
               for key, score in (("M31", 75), ("M42", 65))]
    profile = {"projects": {key: deepcopy(project) for key in ("M31", "M42")}}
    from decision.models.acquisition_intent_selection import AcquisitionIntentSelection, AcquisitionIntentSelectionStatus
    profile["projects"]["M42"]["acquisition_intent_targets"][0]["target_hours"] = 20
    profile["projects"]["M42"]["acquisition_intent_progress"] = [
        {"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": 7200}]
    original = astro_score.compose_acquisition_intent_selection
    def select(**kwargs):
        if kwargs["remaining_progress"][0].acquired_hours is not None:
            return AcquisitionIntentSelection("sh2-129_ha", ("sh2-129_ha",),
                AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT, ("ONLY_ELIGIBLE_INTENT",))
        return original(**kwargs)
    monkeypatch.setattr(astro_score, "compose_acquisition_intent_selection", select)
    before = astro_score.recommend_project_for_night(objects, profile=profile)
    assert before[0].catalog_key == "M42"
    assert before[0].final_score == 77.625
    initial = next(c for c in before if c.catalog_key == "M31")
    assert initial.final_score == 31.5
    for key in removed:
        profile["projects"]["M31"].pop(key)
    after = astro_score.recommend_project_for_night(objects, profile=profile)
    remaining = next((c for c in after if c.catalog_key == "M31"), None)
    assert remaining is None or remaining.final_score <= initial.final_score
    assert remaining is None or remaining.decision_score <= initial.decision_score
    if remaining is None:
        assert after[0].catalog_key == "M42"
        assert after.rejections[0].basis.value == "modern_provenance_missing"

@pytest.mark.parametrize("project", [
    {"hours": 2, "target_hours": 20, "importance": 5},
    {"decision_provenance": "legacy_read_only", "hours": 2, "target_hours": 20},
])
def test_legacy_data_cannot_authorize_new_candidate(project):
    original = deepcopy(project)
    result = astro_score.recommend_project_for_night(
        [{"name": "M31", "global_score": 75}], profile={"projects": {"M31": project}})
    assert not result
    assert result.rejections
    assert project == original


def test_complete_modern_score_and_input_stay_unchanged(monkeypatch, selected_modern_ranking_intent):
    from conftest import modern_ranking_project
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(astro_score.future_engine, "estimate", lambda *a, **k:
                        SimpleNamespace(risk="FAIBLE", opportunity_ratio=1))
    project = modern_ranking_project({"hours": 2, "target_hours": 20, "importance": 5})
    profile = {"projects": {"M31": project}}
    candidates = astro_score.recommend_project_for_night(
        [{"name": "M31", "global_score": 75}], profile=profile)
    assert candidates[0].final_score == 85.67500000000001
    assert candidates[0].selected_acquisition_intent_id == "sh2-129_ha"
    start = datetime(2026, 10, 7, 20, tzinfo=timezone.utc)
    evaluation = {"catalog_key": "M31", "selected_acquisition_intent_id": "sh2-129_ha",
                  "window": {"start": start, "end": start + timedelta(hours=2)}}
    before = astro_score.build_mission_input(evaluation, profile=profile)
    assert before.recommended_hours == 2
    assert before.expected_gain == 10
    for removed in ("imaging_field_id", "acquisition_intent_targets", "acquisition_intent_progress"):
        damaged = deepcopy(profile)
        damaged["projects"]["M31"].pop(removed)
        after = astro_score.build_mission_input(evaluation, profile=damaged)
        assert after.recommended_hours == after.expected_gain == 0
        assert after.selected_filter is None
        assert not astro_score.recommend_project_for_night(
            [{"name": "M31", "global_score": 75}], profile=damaged)


def test_typed_provenance_labels_never_supply_missing_evidence():
    from decision.services.project_decision_provenance import (
        ProjectDecisionProvenance as P, resolve_project_decision_provenance as resolve,
    )
    from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
    resolver = build_production_imaging_field_resolver()
    assert resolve({}, resolver) is P.MODERN_PROVENANCE_MISSING
    assert resolve({"decision_provenance": "modern_authorized"}, resolver) is P.MODERN_PROVENANCE_MISSING
    assert resolve({"decision_provenance": "legacy_read_only"}, resolver) is P.LEGACY_READ_ONLY
    assert resolve({"decision_provenance": "unexpected"}, resolver) is P.MODERN_PROVENANCE_MISSING


def test_legacy_projection_retains_historical_totals_without_new_gain(monkeypatch):
    from datetime import datetime, timedelta, timezone
    project = {"decision_provenance": "legacy_read_only", "hours": 2, "target_hours": 20}
    assert astro_score.project_remaining_hours("M31", {"M31": project}) == 18
    monkeypatch.setattr(astro_score.FilterInventoryLoader, "load", lambda: pytest.fail("legacy promotion"))
    start = datetime(2026, 10, 7, 20, tzinfo=timezone.utc)
    value = astro_score.build_mission_input({"catalog_key": "M31",
        "window": {"start": start, "end": start + timedelta(hours=2)}},
        profile={"projects": {"M31": project}})
    assert value.recommended_hours == value.expected_gain == 0


@pytest.mark.parametrize("label", ["legacy_read_only", "modern_authorized", "unexpected"])
def test_deleting_a_label_cannot_change_positive_modern_proof(label):
    from conftest import modern_ranking_project
    from decision.services.project_decision_provenance import (
        ProjectDecisionProvenance as P, resolve_project_decision_provenance as resolve,
    )
    from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
    project = modern_ranking_project({"hours": 0, "target_hours": 2})
    project["decision_provenance"] = label
    resolver = build_production_imaging_field_resolver()
    assert resolve(project, resolver) is P.MODERN_AUTHORIZED
    project.pop("decision_provenance")
    assert resolve(project, resolver) is P.MODERN_AUTHORIZED


@pytest.mark.parametrize("project", [
    {"hours": 2, "target_hours": 20},
    {"decision_provenance": "legacy_read_only", "hours": 2, "target_hours": 20},
])
def test_cli_runner_cannot_promote_fieldless_project(project):
    from decision.runners.tonight_runner import TonightRunner
    def forbidden(**kwargs):
        pytest.fail("legacy data reached a new recommendation or mission")
    runner = TonightRunner(
        report_runner=SimpleNamespace(run_tonight=forbidden),
        portfolio_forecast_engine=None, build_mission_input=forbidden,
        recommend_project_for_night=astro_score.recommend_project_for_night,
        opportunity_recommendation_service=SimpleNamespace(build=forbidden),
    )
    runner.present_recommended_mission(
        winner={"duration": 2}, top_objects=[{"name": "M31", "global_score": 75}],
        top_nights=[], profile={"projects": {"M31": project}},
    )
