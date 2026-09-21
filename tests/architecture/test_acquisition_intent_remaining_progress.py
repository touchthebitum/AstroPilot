import sys
from dataclasses import FrozenInstanceError
from math import isclose

import pytest
from types import SimpleNamespace
import astro_score

from decision.definitions.production_imaging_fields import (
    IMAGING_FIELD_DEFINITIONS, build_production_imaging_field_resolver,
)
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityAssessment, AcquisitionIntentEligibilityReason,
    AcquisitionIntentEligibilityStatus,
)
from decision.services.acquisition_intent_selection import select_acquisition_intent
from decision.models.project_acquisition_intent_target import ProjectAcquisitionIntentTarget
from decision.services.acquisition_intent_eligibility import evaluate_acquisition_intent_eligibility
from decision.services.acquisition_intent_remaining_progress import derive_acquisition_intent_remaining_progress
from decision.models.candidate_rejection import CandidateRejectionBasis
from decision.models.acquisition_intent_selection import AcquisitionIntentSelectionStatus
from decision.opportunity.action import Action
from decision.opportunity.opportunity_engine import OpportunityEngine
from decision.recommendation.recommendation_engine import RecommendationEngine
from decision.runners.tonight_runner import TonightRunner
from decision.services.opportunity_recommendation_service import OpportunityRecommendationService
from decision.services.project_acquisition_intent_progress import (
    ProjectAcquisitionIntentProgressError, resolve_project_acquisition_intent_progress,
)


FIELD = IMAGING_FIELD_DEFINITIONS[0]
TARGETS = (ProjectAcquisitionIntentTarget("sh2-129_ha", 2),
           ProjectAcquisitionIntentTarget("ou4_oiii", 4))


def derive(entries=(), targets=TARGETS):
    return derive_acquisition_intent_remaining_progress(FIELD, targets, entries)


def test_unknown_zero_manual_detailed_and_overshoot():
    unknown, other = derive()
    assert (unknown.acquired_seconds, unknown.acquired_hours, unknown.remaining_hours) == (None, None, None)
    assert other.remaining_hours is None
    zero, _ = derive(({"acquisition_intent_id": "sh2-129_ha", "acquired_frames": 0, "exposure_seconds": 300},))
    assert (zero.acquired_seconds, zero.acquired_hours, zero.remaining_hours) == (0, 0, 2)
    detailed, _ = derive(({"acquisition_intent_id": "sh2-129_ha", "acquired_frames": 24, "exposure_seconds": 300},))
    assert detailed.completed and detailed.remaining_hours == 0
    manual, _ = derive(({"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": 10800},))
    assert manual.acquired_hours == 3 and manual.remaining_hours == 0
    without_target, _ = derive(({"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": 3600},), ())
    assert without_target.acquired_hours == 1 and without_target.remaining_hours is None
    with pytest.raises(FrozenInstanceError):
        manual.remaining_hours = 5


def test_large_finite_values_do_not_overflow_target_conversion():
    target = (ProjectAcquisitionIntentTarget("sh2-129_ha", sys.float_info.max),)
    item, _ = derive(({"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": sys.float_info.max},), target)
    assert item.remaining_hours > 0


def test_extreme_frames_times_tiny_exposure_remains_finite():
    entry = {"acquisition_intent_id": "sh2-129_ha", "acquired_frames": 10**309,
             "exposure_seconds": 1e-310}
    project = {"imaging_field_id": FIELD.imaging_field_id,
               "acquisition_intent_progress": [entry]}
    validated = resolve_project_acquisition_intent_progress(
        project, build_production_imaging_field_resolver())
    item, _ = derive(validated)
    assert isclose(item.acquired_seconds, 0.1, rel_tol=1e-12)
    assert item.acquired_hours == item.acquired_seconds / 3600
    assert item.remaining_hours == 2 - item.acquired_hours


@pytest.mark.parametrize("entry", [
    {"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": 10**400},
    {"acquisition_intent_id": "sh2-129_ha", "acquired_frames": 10**400,
     "exposure_seconds": 1.0},
])
def test_unrepresentable_seconds_fail_closed_in_validation_and_derivation(entry):
    project = {"imaging_field_id": FIELD.imaging_field_id,
               "acquisition_intent_progress": [entry]}
    with pytest.raises(ProjectAcquisitionIntentProgressError, match="duration must be finite"):
        resolve_project_acquisition_intent_progress(
            project, build_production_imaging_field_resolver())
    with pytest.raises(ValueError, match="duration must be finite"):
        derive((entry,))


def test_completion_precedes_missing_weather_and_equipment_only_when_known():
    complete, unknown = derive(({"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": 7200},))
    def assess(intent, progress):
        return evaluate_acquisition_intent_eligibility(
            acquisition_intent=intent, imaging_field=FIELD, project_targets=TARGETS,
            remaining_progress=progress, setup_filter_capabilities=None,
            productive_window=None, session_availability=None, weather_trust_decision=None,
        )
    completed = assess(FIELD.acquisition_intents[0], complete)
    assert completed.status is AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE
    assert completed.blocking_reasons == (AcquisitionIntentEligibilityReason.INTENT_TARGET_COMPLETED,)
    assert assess(FIELD.acquisition_intents[1], unknown).status is AcquisitionIntentEligibilityStatus.INSUFFICIENT_EVIDENCE
    selected = select_acquisition_intent((
        completed,
        AcquisitionIntentEligibilityAssessment(
            "ou4_oiii", AcquisitionIntentEligibilityStatus.ELIGIBLE, (), (),
        ),
    ), ())
    assert selected.selected_acquisition_intent_id == "ou4_oiii"


def test_candidate_only_rejected_when_every_target_is_conclusively_complete(monkeypatch):
    monkeypatch.setattr(astro_score.future_engine, "estimate", lambda *args, **kwargs: SimpleNamespace(risk="FAIBLE", opportunity_ratio=1))
    project = {"hours": 2, "target_hours": 20, "importance": 5,
               "imaging_field_id": FIELD.imaging_field_id,
               "acquisition_intent_targets": [
                   {"acquisition_intent_id": target.acquisition_intent_id, "target_hours": target.target_hours}
                   for target in TARGETS],
               "acquisition_intent_progress": [
                   {"acquisition_intent_id": "sh2-129_ha", "acquired_duration_manual": 7200}]}
    objects = [{"name": "Sh2-129", "catalog_key": "Sh2-129", "global_score": 75}]
    partial = astro_score.recommend_project_for_night(objects, profile={"projects": {"Sh2-129": project}})
    assert len(partial) == 1 and partial.rejections == ()
    assert partial[0].acquired_hours == 2
    assert partial[0].acquisition_intent_remaining_progress[0].completed
    assert partial[0].acquisition_intent_remaining_progress[1].remaining_hours is None
    project["acquisition_intent_progress"].append(
        {"acquisition_intent_id": "ou4_oiii", "acquired_duration_manual": 14400})
    completed = astro_score.recommend_project_for_night(objects, profile={"projects": {"Sh2-129": project}})
    assert len(completed) == 0
    assert completed.rejections[0].basis is CandidateRejectionBasis.INTENT_TARGETS_COMPLETED


@pytest.mark.parametrize("targeted", [False, True])
def test_legacy_opportunity_recommendation_and_tonight_baselines(monkeypatch, targeted):
    monkeypatch.setattr(astro_score.future_engine, "estimate", lambda *args, **kwargs: SimpleNamespace(risk="FAIBLE", opportunity_ratio=1))
    objects = [{"name": key, "catalog_key": key, "global_score": score}
               for key, score in (("M31", 75), ("M42", 65))]
    projects = {key: {"hours": 2, "target_hours": 20, "importance": 5} for key in ("M31", "M42")}
    if targeted:
        projects["M31"].update(imaging_field_id=FIELD.imaging_field_id,
                               acquisition_intent_targets=[
                                   {"acquisition_intent_id": "sh2-129_ha", "target_hours": 2}])
    profile = {"projects": projects}
    candidates = astro_score.recommend_project_for_night(objects, profile=profile)
    # Historical scoring/ranking constants, not a second invocation of the new path.
    assert candidates.rejections == ()
    assert [(item.catalog_key, item.final_score, item.decision_score, item.acquired_hours)
            for item in candidates] == [
                ("M31", 77.80000000000001, 77.80000000000001, 2.0),
                ("M42", 70.80000000000001, 70.80000000000001, 2.0),
            ]
    if targeted:
        assert candidates[0].acquisition_intent_selection_status is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT
        assert candidates[0].acquisition_intent_remaining_progress[0].remaining_hours is None
        assert candidates[0].acquisition_intent_remaining_progress[0].acquired_hours is None
    else:
        assert all(item.acquisition_intent_selection_status is None for item in candidates)
        assert all(item.acquisition_intent_remaining_progress == () for item in candidates)
    service = OpportunityRecommendationService(
        opportunity_engine=OpportunityEngine(),
        recommendation_engine=RecommendationEngine())
    opportunity = OpportunityEngine().evaluate(candidates=list(candidates))
    assert opportunity.action is Action.CONTINUE_PROJECT
    assert opportunity.candidate.catalog_key == "M31"
    assert [item.catalog_key for item in opportunity.shortlist_entries] == ["M42"]
    recommendation = service.build(candidates=list(candidates))
    assert recommendation.opportunity.candidate.catalog_key == "M31"
    assert recommendation.opportunity.action is Action.CONTINUE_PROJECT
    assert recommendation.confidence is None

    class Report:
        def __init__(self):
            self.calls = []
        def run_tonight(self, **kwargs):
            self.calls.append(kwargs)
        def show_portfolio_completion_forecast(self, roadmap, **kwargs):
            self.roadmap = roadmap

    report = Report()
    runner = TonightRunner(report_runner=report,
                           portfolio_forecast_engine=SimpleNamespace(
                               simulate_dynamic_portfolio_roadmap=lambda **kwargs: []),
                           build_mission_input=lambda *args, **kwargs: None,
                           recommend_project_for_night=astro_score.recommend_project_for_night,
                           opportunity_recommendation_service=service)
    runner.run(top_nights=[{"duration": 3, "top_objects": objects}],
               night_capacities=[], profile=profile)
    assert len(report.calls) == 1
    assert report.calls[0]["recommendation"].opportunity.candidate.catalog_key == "M31"
    assert report.calls[0]["recommendation"].opportunity.action is Action.CONTINUE_PROJECT
    assert report.roadmap == []
