"""Cross-guard audit: project -> MissionInput -> productivity -> authorization.

Only target astrometry is fixed; capacity, weather validation and windowing
are production code. Direct assembly gaps are normal regression tests.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import combinations
from types import SimpleNamespace as NS

import pytest
import astro_score
from decision.mission.mission_assembler import (
    MissionAssembler, ProductiveWindowAssessment, _mission_timing_assessment,
)
from decision.mission.mission_input import MissionInput
from decision.models.session_availability import SessionAvailability as A, SessionAvailabilityMode as M
from decision.weather.weather_forecast import WeatherForecast

START = datetime(2026, 10, 8, 20, tzinfo=timezone.utc)
KEYS = ("imaging_field_id", "acquisition_intent_targets", "acquisition_intent_progress")
MASKS = [combo for n in range(4) for combo in combinations(KEYS, n)]
SERIES = ("hourly_clouds", "hourly_humidity", "hourly_wind", "hourly_seeing", "hourly_moon_penalty")


def project(intent, acquired):
    return {"hours": 0, "target_hours": 100, "importance": 5,
        "imaging_field_id": "sh2-129_ou4",
        "acquisition_intent_targets": [{"acquisition_intent_id": intent, "target_hours": 3}],
        "acquisition_intent_progress": ([] if acquired is None else [
            {"acquisition_intent_id": intent, "acquired_duration_manual": acquired * 3600}])}


def weather():
    # A unique best duration window avoids the intentional ambiguity refusal.
    return WeatherForecast(hourly_clouds=[20., 15., 10., 0.], hourly_humidity=[40.] * 4,
        hourly_wind=[0.] * 4, hourly_seeing=[1.2] * 4, hourly_moon_penalty=[0.] * 4)


def availability(mode):
    return {"all": A(M.ALL_NIGHT), "until": A(M.UNTIL, end=START + timedelta(hours=1.25)),
        "duration": A(M.DURATION, duration=timedelta(hours=1.25)), "missing": None}[mode]


@pytest.fixture(autouse=True)
def astrometry(monkeypatch):
    monkeypatch.setattr("decision.night_productivity.night_conditions_provider.DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: 70.)


def source(value, intent, mode):
    return replace(astro_score.build_mission_input({"catalog_key": "M31",
        "selected_acquisition_intent_id": intent,
        "selected_window_weather": weather(),
        "window": {"start": START, "end": START + timedelta(hours=4)}},
        profile={"projects": {"M31": value}}), availability=availability(mode))


def assess(value):
    context = NS(site=NS(latitude=46.75, longitude=6.55), weather=None, session=None)
    return ProductiveWindowAssessment.build(target="M31", context=context, mission_input=value)


@pytest.mark.parametrize("intent", ["sh2-129_ha", "ou4_oiii"])
@pytest.mark.parametrize("acquired", [0., 1.5, 2.5, 3., None])
@pytest.mark.parametrize("mode", ["all", "until", "duration", "missing"])
@pytest.mark.parametrize("removed", MASKS)
@pytest.mark.parametrize("missing_weather", [None, *SERIES])
def test_composed_evidence_deletion_never_increases_duration_or_gain(intent, acquired, mode, removed, missing_weather):
    value = project(intent, acquired)
    original = deepcopy(value)
    complete = source(value, intent, mode)
    before, _ = _mission_timing_assessment(assess(complete), complete.availability)
    damaged = deepcopy(value)
    for key in removed:
        damaged.pop(key)
    degraded = source(damaged, intent, mode)
    if missing_weather:
        degraded = replace(degraded, weather=replace(degraded.weather, **{missing_weather: None}))
    assessment = assess(degraded)
    after, refusal = _mission_timing_assessment(assessment, degraded.availability)
    assert value == original
    assert degraded.recommended_hours <= complete.recommended_hours
    assert degraded.expected_gain <= complete.expected_gain
    if after:
        assert before is not None
        assert after[2] <= before[2] and after[3] <= before[3]
        remaining = max(0, 3 - acquired)
        cap = min(4, remaining, 1.25 if mode in ("until", "duration") else 4)
        assert after[2] <= cap
        assert after[1] - after[0] == timedelta(hours=after[2])
        assert after[3] == pytest.approx(round(after[2] / 3 * 100, 2))
    if removed or missing_weather or mode == "missing" or acquired is None or acquired >= 2.5:
        assert after is None
        assert refusal is not None
    else:
        assert after is not None  # positive control prevents vacuous all-rejected tests


@pytest.mark.parametrize("removed", MASKS[1:])
def test_all_provenance_subsets_preserve_winner(monkeypatch, selected_modern_ranking_intent, removed):
    monkeypatch.setattr(astro_score.future_engine, "estimate", lambda *a, **k: NS(risk="FAIBLE", opportunity_ratio=1))
    profile = {"projects": {key: project("sh2-129_ha", 0.) for key in ("M31", "M42")}}
    objects = [{"name": key, "catalog_key": key, "global_score": score} for key, score in (("M31", 90), ("M42", 70))]
    before = astro_score.recommend_project_for_night(objects, profile=profile)
    assert before[0].catalog_key == "M31"
    for key in removed:
        profile["projects"]["M31"].pop(key)
    after = astro_score.recommend_project_for_night(objects, profile=profile)
    assert [c.catalog_key for c in after] == ["M42"]
    assert after[0] == before[1]
    assert after.rejections[0].basis.value == "modern_provenance_missing"


@pytest.mark.parametrize("identity", ["none", "field_intent_without_capacity"])
def test_direct_assembler_cannot_authorize_unproven_modern_input(monkeypatch, identity, frozen_equipment):
    # Keep productivity/windowing real. Ancillary reports cannot supply authorization.
    for name in ("ProjectRiskContextBuilder.build", "RiskEngine.evaluate", "SeasonAnalysis.analyze"):
        monkeypatch.setattr("decision.mission.mission_assembler." + name, lambda *a, **k: None)
    monkeypatch.setattr("decision.mission.mission_assembler.DynamicSeasonEngine.target_visibility_window", lambda *a, **k: [])
    context = NS(site=NS(name="Buttes", latitude=46.75, longitude=6.55),
        weather=NS(seeing_arcsec=1.2), session=None,
        equipment=frozen_equipment, sky=NS(target_altitude_deg=70,
            target=NS(name="M31", object_type="galaxy", angular_size_arcmin=190)))
    extra = {} if identity == "none" else dict(imaging_field_id="sh2-129_ou4", acquisition_intent_id="sh2-129_ha")
    value = MissionInput(START, START + timedelta(hours=4), 4, weather(), 0, 4, 100,
        availability=A(M.ALL_NIGHT), **extra)
    mission = MissionAssembler.build("M31", NS(positives=[], negatives=[], confidence=1), context, [], [], mission_input=value)
    assert mission is None


@pytest.fixture
def assembly_environment(monkeypatch, frozen_equipment):
    for name in ("ProjectRiskContextBuilder.build", "RiskEngine.evaluate", "SeasonAnalysis.analyze"):
        monkeypatch.setattr("decision.mission.mission_assembler." + name, lambda *a, **k: None)
    monkeypatch.setattr("decision.mission.mission_assembler.DynamicSeasonEngine.target_visibility_window", lambda *a, **k: [])
    return dict(target="Sh2-129", summary=NS(positives=[], negatives=[], confidence=1),
        context=NS(site=NS(name="Buttes", latitude=46.75, longitude=6.55),
            weather=NS(seeing_arcsec=1.2), session=None, equipment=frozen_equipment,
            sky=NS(target_altitude_deg=70, target=NS(name="Sh2-129", object_type="nebula", angular_size_arcmin=190))),
        equipment=[], alternatives=[])


def modern_source(acquired=0, *, equipment="samyang_183", removed=(), intent="sh2-129_ha"):
    value = project(intent, acquired)
    for key in removed:
        value.pop(key)
    return replace(astro_score.build_mission_input({"catalog_key": "Sh2-129",
        "selected_acquisition_intent_id": intent, "selected_window_weather": weather(),
        "window": {"start": START, "end": START + timedelta(hours=4)}},
        profile={"active_equipment": equipment, "projects": {"Sh2-129": value}}), availability=availability("all"))


@pytest.mark.parametrize("intent", ["sh2-129_ha", "ou4_oiii"])
@pytest.mark.parametrize("acquired", [0, 1.5, 2, 2.01, 2.5, 3, None])
@pytest.mark.parametrize("removed", MASKS)
@pytest.mark.parametrize("equipment", ["samyang_183", None, "unknown"])
def test_modern_creation_cross_boundary_matrix(assembly_environment, intent, acquired, removed, equipment):
    value = modern_source(acquired, equipment=equipment, removed=removed, intent=intent)
    mission = MissionAssembler.build(**assembly_environment, mission_input=value)
    authorized = not removed and equipment == "samyang_183" and acquired is not None and acquired <= 2
    if not authorized:
        assert mission is None
    else:
        assert mission is not None
        assert mission.recommended_hours <= min(4, 3 - acquired)
        assert mission.expected_gain == round(mission.recommended_hours / 3 * 100, 2)


@pytest.mark.parametrize("damage", ["identity", "intent", "capacity", "authority", "availability", "preview"])
def test_authorization_is_bound_and_cannot_be_reused_after_evidence_deletion(assembly_environment, damage):
    value = modern_source()
    changes = {"identity": dict(imaging_field_id=None), "intent": dict(acquisition_intent_id=None, acquisition_capacity=None),
        "capacity": dict(acquisition_capacity=None), "authority": dict(creation_authorization=True),
        "availability": dict(availability=None), "preview": dict(evidence_only=True)}[damage]
    value = replace(value, **changes)
    if damage == "preview":
        with pytest.raises(ValueError, match="preselection_evidence"):
            MissionAssembler.build(**assembly_environment, mission_input=value)
    else:
        result = MissionAssembler.build(**assembly_environment, mission_input=value, _include_actionability_diagnostic=True)
        assert result.mission is None
        assert result.creation_refusal or result.actionability_refusal.cause_code


def test_mismatched_capacity_rejected_before_creation():
    value = modern_source()
    with pytest.raises(ValueError, match="acquisition_capacity_intent_mismatch"):
        replace(value, acquisition_capacity=replace(value.acquisition_capacity, acquisition_intent_id="ou4_oiii"))


def test_authorization_has_no_public_boolean_constructor():
    from decision.mission.modern_mission_authorization import ModernMissionAuthorization
    with pytest.raises(TypeError, match="internal_factory"):
        ModernMissionAuthorization(imaging_field_id="sh2-129_ou4", acquisition_intent_id="sh2-129_ha",
            acquisition_capacity=modern_source().acquisition_capacity, filter_profile_id="baader_ha_highspeed_6_5nm")


def test_preview_evaluates_physics_without_returning_engaging_mission(assembly_environment):
    value = MissionInput(START, START + timedelta(hours=4), 4, weather(), 0, 4, 0, evidence_only=True)
    preview = MissionAssembler.preview(target="Sh2-129", context=assembly_environment["context"], mission_input=value)
    assert isinstance(preview, ProductiveWindowAssessment)
    assert preview.productivity.productive_hours > 0
    assert not hasattr(preview, "mission_id")


def test_normal_service_and_builder_share_creation_guard(assembly_environment):
    from decision.mission.mission_builder import NightMissionBuilder
    from decision.services.tonight_mission_service import TonightMissionService
    value = modern_source()
    context = assembly_environment["context"]
    summary = assembly_environment["summary"]
    service = TonightMissionService(build_mission=NightMissionBuilder.build)
    kwargs = dict(winner={"object_evaluations": {"Sh2-129": {}}},
        objects=[dict(name="Sh2-129", decision_context=context, decision_summary=summary)], recommended_key="Sh2-129")
    assert service.create(**kwargs, build_mission_input=lambda _: value) is not None
    assert service.create(**kwargs, build_mission_input=lambda _: replace(value, creation_authorization=None)) is None


def test_complete_raw_input_still_requires_factory_authorization(assembly_environment):
    value = modern_source()
    raw = replace(value, creation_authorization=None)
    result = MissionAssembler.build(**assembly_environment, mission_input=raw, _include_actionability_diagnostic=True)
    assert result.mission is None
    assert result.creation_refusal == "modern_mission_authorization_required"


def test_internal_factory_rederives_capacity_instead_of_trusting_supplied_total():
    from decision.mission.modern_mission_authorization import _issue_from_project
    value = modern_source()
    forged = replace(value, acquisition_capacity=replace(value.acquisition_capacity, remaining_hours=30))
    assert _issue_from_project(forged, profile={"active_equipment": "samyang_183",
        "projects": {"Sh2-129": project("sh2-129_ha", 0)}}, catalog_key="Sh2-129") is None
