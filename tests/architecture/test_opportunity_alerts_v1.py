"""Alert contract: real modern authority, productivity and session windowing."""
from dataclasses import replace
from copy import copy
from datetime import timedelta

import pytest

from test_modern_mission_authorization import (
    START, assembly_environment, astrometry, modern_source,
)
from decision.mission.mission_assembler import MissionAssembler
from decision.models.candidate import Candidate
from decision.models.acquisition_intent_assessment import AcquisitionIntentAssessment
from decision.models.acquisition_intent_eligibility import AcquisitionIntentEligibilityStatus as Eligibility
from decision.models.acquisition_intent_selection import AcquisitionIntentSelectionStatus as Selection
from decision.opportunity.opportunity import Opportunity
from decision.opportunity.action import Action
from decision.recommendation.recommendation import Recommendation
from decision.services.tonight_application_service import TonightResult, _live_alert_result
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import WeatherForecastPoint, WeatherLocation, WeatherValue, WeatherVariable, CANONICAL_UNITS
from decision.models.opportunity_alert import OpportunityAlertPolicy, OpportunityAlertStatus
from decision.services.opportunity_alert_service import OpportunityAlertService, InMemoryOpportunityAlertLedger


@pytest.fixture
def complete(assembly_environment):
    value = modern_source()
    value = replace(value, weather=replace(value.weather, hourly_temperature=[10.] * 4),
                    mission_id="mission", decision_id="decision", selection_id="selection")
    assembly = MissionAssembler.build(**{**assembly_environment, "equipment": ["samyang_183"]},
        mission_input=value, _include_actionability_diagnostic=True)
    candidate = Candidate(name="Sh2-129", catalog_key="Sh2-129", priority=5,
        astro_score=90, final_score=90, decision_score=90, portfolio_score=90,
        global_score=90, setup_score=90, best_setup="samyang_183", closure_bonus=0,
        imaging_field_id=value.imaging_field_id, selected_acquisition_intent_id=value.acquisition_intent_id,
        viable_acquisition_intent_ids=(value.acquisition_intent_id,),
        acquisition_intent_selection_status=Selection.SINGLE_ELIGIBLE_INTENT,
        acquisition_intent_assessments=(AcquisitionIntentAssessment(value.acquisition_intent_id,
            "ha", "Ha", Eligibility.ELIGIBLE, ()),))
    location = WeatherLocation(46.75, 6.55)
    evidence = DecisionForecastEvidence(tuple(WeatherForecastPoint("open-meteo", START, START + timedelta(hours=h),
        location, location, tuple(WeatherValue(v, number, CANONICAL_UNITS[v]) for v, number in (
            (WeatherVariable.CLOUD_COVER_PERCENT, 10), (WeatherVariable.RELATIVE_HUMIDITY_PERCENT, 40),
            (WeatherVariable.WIND_SPEED_KMH, 0), (WeatherVariable.TEMPERATURE_C, 10)))) for h in range(4)))
    result = TonightResult({}, Recommendation(Opportunity(Action.CONTINUE_PROJECT, candidate), 1), assembly.mission,
        forecast_evidence=evidence, timeline_start=value.window_start, alert_mission_input=value, alert_assessment=assembly.assessment)
    return _live_alert_result(result)


@pytest.fixture
def policy(complete):
    return OpportunityAlertPolicy(enabled=True, site_name="Buttes", project_keys=("Sh2-129",),
        intent_ids=("sh2-129_ha",), filter_profile_ids=(complete.alert_mission_input.creation_authorization.filter_profile_id,))


def decide(result, policy, ledger=None, at=START):
    return OpportunityAlertService(ledger or InMemoryOpportunityAlertLedger()).evaluate(
        result=result, policy=policy, logical_time=at)


def test_complete_alert(complete, policy):
    decision = decide(complete, policy)
    assert decision.status is OpportunityAlertStatus.ALERT
    assert decision.alert.expected_gain > 0
    assert decision.alert.duration_minutes >= 60
    assert decision.alert.kind == "session_opportunity"


@pytest.mark.parametrize("damage", ["recommendation", "mission", "availability", "authority", "profile",
    "short", "gain_zero", "gain_negative", "gain_nan", "intent", "assessment", "weather",
    "forecast_evidence", "windows", "partial_aqi", "aqi_unknown", "lineage", "refusal", "legacy", "read_only"])
def test_missing_or_incoherent_evidence_fails_closed(complete, policy, damage):
    result = complete
    value = result.alert_mission_input
    mission = result.mission
    if damage in ("recommendation", "mission", "forecast_evidence"):
        result = replace(result, **{damage: None})
    elif damage in ("availability", "authority", "weather"):
        key = {"authority": "creation_authorization"}.get(damage, damage)
        result = replace(result, alert_mission_input=replace(value, **{key: None}))
    elif damage == "profile":
        authority = copy(value.creation_authorization)
        object.__setattr__(authority, "filter_profile_id", "")
        result = replace(result, alert_mission_input=replace(value, creation_authorization=authority))
    elif damage == "short":
        result = replace(result, mission=replace(mission, window_end=mission.window_start + timedelta(minutes=59), recommended_hours=59/60))
    elif damage.startswith("gain_"):
        result = replace(result, mission=replace(mission, expected_gain={"gain_zero": 0, "gain_negative": -1, "gain_nan": float("nan")}[damage]))
    elif damage == "intent":
        result = replace(result, mission=replace(mission, acquisition_intent_id="other"))
    elif damage == "assessment":
        result = replace(result, alert_assessment=replace(result.alert_assessment, evidence_issues=("missing_weather",)))
    elif damage == "windows":
        result = replace(result, mission=replace(mission, productivity=replace(mission.productivity, windows=[])))
    elif damage in ("partial_aqi", "aqi_unknown"):
        result = replace(result, mission=replace(mission, astro_quality=None if damage == "aqi_unknown" else replace(
            mission.astro_quality, decision_eligible=False, completeness=.8, decision_score=None, status="insufficient_evidence")))
    elif damage == "lineage":
        result = replace(result, mission=replace(mission, decision_id="other"))
    elif damage == "refusal":
        result = replace(result, actionability_refusal=object())
    elif damage in ("legacy", "read_only"):
        result = replace(result, alert_live_marker=None, alert_mission_input=None if damage == "legacy" else value)
    assert decide(result, policy).status is OpportunityAlertStatus.NO_ALERT


@pytest.mark.parametrize("field", ["recommendation", "mission", "alert_assessment", "alert_mission_input", "alert_live_marker"])
def test_deleting_evidence_never_promotes_refusal(complete, policy, field):
    strict = replace(policy, min_expected_gain=1000)
    assert decide(complete, strict).alert is None
    assert decide(replace(complete, **{field: None}), strict).alert is None


@pytest.mark.parametrize("restriction", [dict(enabled=False), dict(min_expected_gain=1000),
    dict(min_duration_minutes=300), dict(min_quality=100), dict(site_name="other"),
    dict(project_keys=("other",)), dict(intent_ids=("other",)), dict(filter_profile_ids=("other",)),
    dict(window_start=START + timedelta(days=1)), dict(window_end=START)])
def test_stricter_policy_cannot_promote_alert(complete, policy, restriction):
    assert decide(complete, policy).alert is not None
    assert decide(complete, replace(policy, **restriction)).alert is None


def test_exact_and_lineage_deduplication(complete, policy):
    ledger = InMemoryOpportunityAlertLedger()
    first = decide(complete, policy, ledger)
    assert first.alert is not None
    assert decide(complete, policy, ledger, START + timedelta(hours=1)).alert is None
    value = replace(complete.alert_mission_input, decision_id="new", selection_id="new")
    changed = replace(complete, alert_mission_input=value, mission=replace(complete.mission, decision_id="new", selection_id="new"))
    assert decide(changed, policy, ledger, START + timedelta(hours=2)).alert is None
    shift = timedelta(days=1)
    changed = replace(changed, timeline_start=changed.timeline_start + shift,
        alert_mission_input=replace(value, window_start=value.window_start + shift, window_end=value.window_end + shift),
        alert_assessment=replace(changed.alert_assessment, window_start=value.window_start + shift, window_end=value.window_end + shift),
        mission=replace(changed.mission, window_start=changed.mission.window_start + shift, window_end=changed.mission.window_end + shift))
    assert decide(changed, policy, ledger, START + shift).alert is not None
    assert decide(complete, policy, ledger, START - timedelta(hours=1)).alert is None


@pytest.mark.parametrize("change", [dict(min_duration_minutes=59), dict(min_quality=float("nan")),
    dict(min_expected_gain=-1), dict(schema_version=2), dict(project_keys=()), dict(cooldown_minutes=0)])
def test_invalid_policy_rejected(policy, change):
    with pytest.raises((ValueError, TypeError)):
        replace(policy, **change)


def test_past_session_never_alerts(complete, policy):
    assert decide(complete, policy, at=START + timedelta(days=1)).alert is None


def test_claim_is_atomic_under_concurrent_cycles(complete, policy):
    from concurrent.futures import ThreadPoolExecutor
    ledger = InMemoryOpportunityAlertLedger()
    with ThreadPoolExecutor(max_workers=8) as pool:
        decisions = list(pool.map(lambda _: decide(complete, policy, ledger), range(32)))
    assert sum(item.alert is not None for item in decisions) == 1


def test_default_policy_is_disabled(complete):
    assert decide(complete, OpportunityAlertPolicy()).alert is None


def test_refusal_does_not_consume_idempotency(complete, policy):
    ledger = InMemoryOpportunityAlertLedger()
    assert decide(complete, replace(policy, min_expected_gain=1000), ledger).alert is None
    assert decide(complete, policy, ledger).alert is not None


def test_live_application_integration_consumes_outputs_without_recalculation(complete, policy, assembly_environment, monkeypatch):
    from types import SimpleNamespace as NS
    from decision.forecast.forecast_run import ForecastRun
    from decision.services.tonight_application_service import TonightApplicationService
    from decision.services.tonight_mission_service import TonightMissionService
    calls = []
    def build_with_diagnostic(**kwargs):
        calls.append("assembly")
        return MissionAssembler.build(**{**assembly_environment, "equipment": ["samyang_183"], **kwargs},
            _include_actionability_diagnostic=True)
    night = {"date": START.date(), "duration": 4, "top_objects": [dict(name="Sh2-129", catalog_key="Sh2-129",
        decision_summary=assembly_environment["summary"], decision_context=assembly_environment["context"])],
        "object_evaluations": {"Sh2-129": {}}}
    app = TonightApplicationService(forecast_nights=lambda *a, **kw: ForecastRun((night,), complete.forecast_evidence),
        build_candidates=lambda *a, **kw: [complete.recommendation.opportunity.candidate],
        opportunity_recommendation_service=NS(build=lambda **kw: complete.recommendation),
        tonight_mission_service=TonightMissionService(None, build_with_diagnostic),
        build_mission_input=lambda *a, **kw: complete.alert_mission_input)
    result = app.evaluate(profile={"location": {"name": "Buttes", "latitude": 46.75, "longitude": 6.55},
        "active_equipment": "samyang_183", "available_equipment": ["samyang_183"]}, weather=None,
        reference_time_utc=START, bortle=4, availability=complete.alert_mission_input.availability)
    assert calls == ["assembly"]
    def forbidden(*a, **kw):
        raise AssertionError("Alert must consume existing evaluation")
    monkeypatch.setattr("decision.mission.mission_assembler.ProductiveWindowAssessment.build", forbidden)
    monkeypatch.setattr("decision.quality.astro_quality_engine.AstroQualityEngine.evaluate", forbidden)
    assert decide(result, policy).alert is not None
    # An ordinary/historical result with identical public data has no live authority.
    assert decide(TonightResult(result.night, result.recommendation, result.mission), policy).alert is None


@pytest.mark.parametrize("series", ["hourly_clouds", "hourly_humidity", "hourly_wind", "hourly_seeing", "hourly_moon_penalty", "hourly_temperature"])
@pytest.mark.parametrize("replacement", [None, [], [float("nan")]])
def test_partial_weather_never_alerts(complete, policy, series, replacement):
    value = complete.alert_mission_input
    damaged = replace(complete, alert_mission_input=replace(value, weather=replace(value.weather, **{series: replacement})))
    assert decide(damaged, policy).alert is None


def test_missing_intent_assessment_never_alerts(complete, policy):
    candidate = replace(complete.recommendation.opportunity.candidate, acquisition_intent_assessments=())
    recommendation = replace(complete.recommendation, opportunity=replace(complete.recommendation.opportunity, candidate=candidate))
    assert decide(replace(complete, recommendation=recommendation), policy).alert is None


def test_logical_time_requires_explicit_timezone(complete, policy):
    with pytest.raises(ValueError, match="aware"):
        decide(complete, policy, at=START.replace(tzinfo=None))
