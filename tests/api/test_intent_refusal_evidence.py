"""Synthetic inputs, real intent gates and archive. Never reconstruct operator evidence."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from astropilot.analysis_history import FileAnalysisHistory
from astropilot.app import create_app, TonightResponseModel
from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.models.acquisition_intent_remaining_progress import AcquisitionIntentRemainingProgress
from decision.models.equipment.setup_filter_capabilities import SetupFilterCapabilities
from decision.models.project_acquisition_intent_target import ProjectAcquisitionIntentTarget
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.night_productivity.productivity_diagnostics import ProductivityBreakdown, ProductivityLosses
from decision.forecast.forecast_run import ForecastRun
from decision.services.acquisition_intent_composition import compose_acquisition_intent_selection
from decision.services.session_availability_windowing import evaluate_physical_productive_window
from decision.services.tonight_application_service import TonightApplicationService, TonightStatus
from decision.services.tonight_response import TonightResponse
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import WeatherForecastPoint, WeatherLocation, WeatherValue, WeatherVariable
from decision.weather.weather_trust_decision import WeatherTrustDecision, WeatherEvidenceQuality, WeatherDecisionAdmissibility
from test_tonight_api import make_result, valid_profile, DEFAULT_WEATHER, DEFAULT_WEATHER_REFERENCE_TIME
from test_profile_backup import source

START = datetime(2026, 10, 27, 4, tzinfo=timezone(timedelta(hours=1)))
AVAILABILITY = SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)
TRUST = WeatherTrustDecision(WeatherEvidenceQuality.SUFFICIENT, WeatherDecisionAdmissibility.ADMISSIBLE, ())


def assessment(stage, *, breakdown=True):
    productive = stage != "no_productive_slice"
    minutes = 30 if productive else 0
    if stage == "eligible":
        minutes = 60
    window = ProductiveWindowAssessment(
        window_start=START, window_end=START + timedelta(hours=2),
        recommended_hours=2, expected_gain=0,
        productivity=NS(windows=(NS(start_hour=0., end_hour=minutes / 60,
                                    productivity=.9, productive=True),) if productive else ()),
        productivity_breakdown=ProductivityBreakdown(
            evaluated_slice_count=8, productive_slice_count=minutes // 15,
            best_slice_start=START, best_slice_end=START + timedelta(minutes=15),
            best_slice_score=.9 if productive else .55, best_slice_tie_count=1,
            productive_slice_threshold=.70,
            losses=ProductivityLosses(cloud=0., moon=0. if productive else .4,
                                      altitude=0., humidity=0. if productive else .05,
                                      wind=.1 if productive else 0.),
        ) if breakdown else None,
    )
    return window


def composed_candidate(window, *, field_id="m42", key="M42"):
    field = build_production_imaging_field_resolver().resolve(field_id)
    targets = tuple(ProjectAcquisitionIntentTarget(intent.acquisition_intent_id, 15)
                    for intent in field.acquisition_intents)
    selected = compose_acquisition_intent_selection(
        imaging_field=field, project_targets=targets,
        remaining_progress=tuple(AcquisitionIntentRemainingProgress(t.acquisition_intent_id, 0, 0, 15, 15) for t in targets),
        setup_filter_capabilities=SetupFilterCapabilities("test", ("Ha", "OIII")),
        productive_window=window, session_availability=AVAILABILITY, weather_trust_decision=TRUST,
        site=None, filter_profile_resolver=Mock(), evidence_builder=Mock(), contamination_estimator=Mock(),
    )
    assert selected.status.value == "no_eligible_intent"
    base = make_result().recommendation.opportunity.candidate
    return replace(base, name=key, catalog_key=key, best_setup="samyang_183", imaging_field_id=field_id,
                   acquisition_intent_selection_status=selected.status,
                   acquisition_intent_assessments=selected.acquisition_intent_assessments)


def service_for(candidate):
    location = WeatherLocation(46.7508, 6.5495)
    points = tuple(WeatherForecastPoint(
        provider_id="synthetic", retrieved_at_utc=START - timedelta(hours=1), forecast_for_utc=START + timedelta(hours=i),
        requested_location=location, grid_location=location,
        values=(WeatherValue(WeatherVariable.CLOUD_COVER_PERCENT, 0, "%"),
                WeatherValue(WeatherVariable.RELATIVE_HUMIDITY_PERCENT, humidity, "%")),
    ) for i, humidity in enumerate((95, 93)))
    night = {"date": "2026-10-26", "top_objects": [{"catalog_key": candidate.catalog_key}],
             "object_evaluations": {candidate.catalog_key: {"window": {"start": START, "end": START + timedelta(hours=2)}}}}
    rec = make_result().recommendation
    mission_gate = Mock(side_effect=AssertionError("A refused acquisition must not reach mission creation"))
    service = TonightApplicationService(
        forecast_nights=lambda *a, **k: ForecastRun([night], DecisionForecastEvidence(points)),
        build_candidates=lambda *a, **k: [candidate],
        opportunity_recommendation_service=NS(build=lambda **k: replace(rec, opportunity=replace(rec.opportunity, candidate=candidate))),
        tonight_mission_service=mission_gate, build_mission_input=mission_gate,
    )
    return service, mission_gate


@pytest.mark.parametrize("stage,minutes", [("no_productive_slice", 0), ("continuous_window_too_short", 30)])
def test_saved_ha_intent_preserves_exact_computed_refusal_through_application_and_api(stage, minutes):
    window = assessment(stage)
    computed = evaluate_physical_productive_window(window, AVAILABILITY).refusal
    candidate = composed_candidate(window)
    evidence = candidate.acquisition_intent_assessments[0].actionability_refusal
    assert evidence == computed
    assert evidence.productivity_breakdown is window.productivity_breakdown
    assert evidence.best_productive_window_minutes == minutes
    assert evidence.required_continuous_minutes == 60
    service, gate = service_for(candidate)
    profile = {**valid_profile(), "projects": {"M42": {"hours": 0, "target_hours": 15}}}
    before = deepcopy(profile)
    result = service.evaluate(profile=profile, weather=object(), reference_time_utc=START,
                              bortle=4, availability=AVAILABILITY, selected_project_id="M42")
    assert result.status is TonightStatus.NO_MISSION and result.mission is None
    assert result.creation_refusal == "no_eligible_acquisition_intent"
    assert result.actionability_refusal is evidence
    body = TonightResponse.from_result(result).to_dict()
    transported = TonightResponseModel.model_validate(body).model_dump(mode="json")
    detail = transported["acquisition_intent_assessments"][0]
    assert detail["acquisition_intent_id"] == "m42_ha"
    assert detail["reason_codes"] == ["insufficient_actionable_productive_window"]
    assert detail["actionability_refusal"] == transported["actionability_refusal"]
    assert transported["actionability_refusal"]["refusal_stage"] == stage
    assert transported["actionability_refusal"]["productivity_breakdown"]["losses"]["cloud"] == 0
    assert transported["refusal_weather"]["cloud_cover_min"] == transported["refusal_weather"]["cloud_cover_max"] == 0
    assert transported["recommended_hours"] == 0 and profile == before
    gate.assert_not_called()


def test_multiple_intents_keep_their_own_diagnostics_without_a_global_attribution():
    candidate = composed_candidate(assessment("continuous_window_too_short"), field_id="sh2-129_ou4", key="Sh2-129")
    ha, oiii = candidate.acquisition_intent_assessments
    oiii = replace(oiii, actionability_refusal=evaluate_physical_productive_window(assessment("no_productive_slice"), AVAILABILITY).refusal)
    candidate = replace(candidate, acquisition_intent_assessments=(ha, oiii))
    service, _ = service_for(candidate)
    result = service.evaluate(profile=valid_profile(), weather=object(), reference_time_utc=START,
                              bortle=4, availability=AVAILABILITY)
    assert result.actionability_refusal is None
    body = TonightResponseModel.model_validate(TonightResponse.from_result(result).to_dict()).model_dump(mode="json")
    assert [a["actionability_refusal"]["refusal_stage"] for a in body["acquisition_intent_assessments"]] == ["continuous_window_too_short", "no_productive_slice"]


def test_missing_detailed_breakdown_stays_missing_and_sixty_minute_rule_is_unchanged():
    candidate = composed_candidate(assessment("no_productive_slice", breakdown=False))
    evidence = candidate.acquisition_intent_assessments[0].actionability_refusal
    assert evidence.refusal_stage.value == "no_productive_slice"
    assert evidence.productivity_breakdown is None and evidence.limiting_factors == ()
    assert evaluate_physical_productive_window(assessment("eligible"), AVAILABILITY).refusal is None


def test_public_contract_rejects_mismatched_global_and_per_intent_diagnostics():
    from pydantic import ValidationError
    candidate = composed_candidate(assessment("no_productive_slice"))
    service, _ = service_for(candidate)
    result = service.evaluate(profile=valid_profile(), weather=object(), reference_time_utc=START,
                              bortle=4, availability=AVAILABILITY)
    payload = TonightResponse.from_result(result).to_dict()
    payload["acquisition_intent_assessments"][0]["actionability_refusal"] = None
    with pytest.raises(ValidationError, match="unselected_intent_refusal_evidence_mismatch"):
        TonightResponseModel.model_validate(payload)


def test_old_v11_lineage_remains_readable_without_reconstruction_and_v12_retains_evidence(tmp_path):
    import json
    from astropilot.decision_acceptance_lineage_store import FileDecisionAcceptanceLineageStore
    from tests.architecture.test_decision_acceptance_lineage_persistence import context
    candidate = composed_candidate(assessment("no_productive_slice"))
    original = context()
    current = replace(original, recommendation=replace(original.recommendation,
        opportunity=replace(original.recommendation.opportunity, candidate=candidate)))
    store = FileDecisionAcceptanceLineageStore(tmp_path / "current")
    store.create_context(current)
    path = tmp_path / "current/decision-1.json"
    before = path.read_bytes()
    assert store.load_context("decision-1").recommendation.opportunity.candidate.acquisition_intent_assessments == candidate.acquisition_intent_assessments
    assert path.read_bytes() == before
    document = json.loads(before)
    assert document["schema_version"] == 12
    document["schema_version"] = 11
    def strip(value):
        if isinstance(value, dict):
            if value.get("class") == "decision.models.acquisition_intent_assessment.AcquisitionIntentAssessment":
                value["fields"].pop("actionability_refusal", None)
            for child in value.values(): strip(child)
        elif isinstance(value, list):
            for child in value: strip(child)
    strip(document)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    legacy_path = legacy / "decision-1.json"
    legacy_path.write_text(json.dumps(document))
    before_legacy = legacy_path.read_bytes()
    loaded = FileDecisionAcceptanceLineageStore(legacy).load_context("decision-1")
    diagnostic = loaded.recommendation.opportunity.candidate.acquisition_intent_assessments[0]
    assert diagnostic.actionability_refusal is None
    assert diagnostic.reason_codes == ("insufficient_actionable_productive_window",)
    assert legacy_path.read_bytes() == before_legacy


def browser_fixtures():
    records = []
    for stage in ("no_productive_slice", "continuous_window_too_short"):
        service, _ = service_for(composed_candidate(assessment(stage)))
        result = replace(service.evaluate(profile=valid_profile(), weather=object(), reference_time_utc=START,
                                          bortle=4, availability=AVAILABILITY), decision_id="synthetic-" + stage)
        body = TonightResponseModel.model_validate(TonightResponse.from_result(result).to_dict()).model_dump(mode="json")
        records.append({"decision_id": body["decision_id"], "created_at_utc": START.astimezone(timezone.utc).isoformat(),
                        "request": {"selected_project_id": "M42", "availability": {"mode": "all_night"}}, "result": body})
    legacy = deepcopy(records[0]);legacy["decision_id"] = legacy["result"]["decision_id"] = "synthetic-legacy"
    legacy["result"]["actionability_refusal"] = None
    for item in legacy["result"]["acquisition_intent_assessments"]:
        item.pop("actionability_refusal", None)
    records.append(legacy)
    return {"records": records}


def test_backup_restore_keeps_new_refusal_and_old_reports_byte_for_byte(source, tmp_path):
    from test_saved_observation_catalogue import seed
    from tests.architecture.test_outcome_evaluation_persistence_contract import evaluation
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    from astropilot.profile_backup import create_backup, inspect_backup, restore_empty, snapshot
    seed(source)
    evaluations = FileOutcomeEvaluationStore(source / "outcome_evaluations")
    for i in range(3):
        evaluations.save(evaluation=evaluation(execution=False, comparison_id=str(i + 1) * 64))
    store = FileAnalysisHistory(source / "analysis_history")
    for record in browser_fixtures()["records"]:
        store.save(key=record["decision_id"], created_at=datetime.fromisoformat(record["created_at_utc"]),
                   request=record["request"], result=record["result"])
    before = snapshot(source)
    raw, summary = create_backup(source)
    files, _ = inspect_backup(raw)
    assert summary == {"projects": 1, "sessions": 0, "observations": 3, "comparisons": 3}
    destination = tmp_path / "restored"
    restore_empty(destination, files)
    assert snapshot(destination) == before == snapshot(source)
    restored = FileAnalysisHistory(destination / "analysis_history")
    for record in browser_fixtures()["records"]:
        assert restored.load(record["decision_id"]) == store.load(record["decision_id"])


def test_full_production_pipeline_saved_M42_all_night_with_synthetic_clear_humid_forecast(tmp_path, monkeypatch):
    """Real candidate builder and astronomy; synthetic forecast, not the Windows report."""
    from astropilot.user_profile import save_user_profile
    from test_saved_observation_catalogue import seed
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    profile = valid_profile()
    profile["projects"] = {"M42": {"hours": 0, "target_hours": 15, "imaging_field_id": "m42",
        "acquisition_intent_targets": [{"acquisition_intent_id": "m42_ha", "target_hours": 15}],
        "acquisition_intent_progress": [{"acquisition_intent_id": "m42_ha", "acquired_duration_manual": 0}]}}
    save_user_profile(profile)
    seed(tmp_path)
    protected = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")}
    reference = datetime(2026, 10, 26, 18, tzinfo=timezone.utc)
    start = datetime(2026, 10, 26, tzinfo=timezone.utc)
    times = [start + timedelta(hours=i) for i in range(72)]
    values = {"cloud_cover": 0, "cloud_cover_low": 0, "cloud_cover_mid": 0, "cloud_cover_high": 0,
              "precipitation": 0, "relative_humidity_2m": 95, "visibility": 20000,
              "wind_speed_10m": 5, "temperature_2m": 6}
    hourly = {name: [value] * len(times) for name, value in values.items()}
    hourly["time"] = [int(t.timestamp()) for t in times]
    weather = replace(DEFAULT_WEATHER, retrieved_at_utc=reference, payload={"hourly": hourly},
                      valid_from=start, valid_until=times[-1], hour_count=len(times))
    with TestClient(create_app(weather_provider=lambda *a: weather, clock=lambda: reference)) as client:
        response = client.post("/v1/tonight", json={"selected_project_id": "M42", "availability": {"mode": "all_night"}})
        assert response.status_code == 200, response.text
        body = response.json()
    assert body["status"] == "no_mission" and body["creation_refusal"] == "no_eligible_acquisition_intent"
    evidence = body["actionability_refusal"]
    assert evidence is not None and evidence["required_continuous_minutes"] == 60
    assert evidence["refusal_stage"] in {"no_productive_slice", "continuous_window_too_short"}
    assert evidence["productivity_breakdown"] is not None
    assert body["acquisition_intent_assessments"][0]["acquisition_intent_id"] == "m42_ha"
    assert body["acquisition_intent_assessments"][0]["actionability_refusal"] == evidence
    from decision.acceptance_lineage_persistence import deserialize_decision_acceptance_aggregate
    lineages = list((tmp_path / "decision_lineage").glob("*.json"))
    assert len(lineages) == 1
    aggregate = deserialize_decision_acceptance_aggregate(lineages[0].read_text())
    assert aggregate.selections == aggregate.missions == ()
    assert aggregate.context.decision_context.primary_catalog_key is None
    saved_candidate = aggregate.context.recommendation.opportunity.candidate
    assert saved_candidate.acquisition_intent_assessments[0].actionability_refusal is not None
    assert saved_candidate.acquisition_intent_assessments[0].actionability_refusal.refusal_stage.value == evidence["refusal_stage"]
    assert all((tmp_path / name).read_bytes() == raw for name, raw in protected.items())
    before_read = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")}
    def forbidden(*a, **k):
        raise AssertionError("No live forecast or eligibility computation is allowed on archive read")
    restarted = TestClient(create_app(service_factory=forbidden, profile_provider=forbidden, weather_provider=forbidden))
    reread = restarted.get("/v1/analysis-history/" + body["decision_id"])
    assert reread.status_code == 200 and reread.json()["result"] == body
    assert before_read == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")}


@pytest.mark.parametrize("stage", ["no_productive_slice", "continuous_window_too_short"])
def test_live_refusal_archive_restart_preserves_three_observations_and_comparisons(tmp_path, monkeypatch, stage):
    from test_saved_observation_catalogue import seed
    from tests.architecture.test_outcome_evaluation_persistence_contract import evaluation
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    seed(tmp_path)
    evaluations = FileOutcomeEvaluationStore(tmp_path / "outcome_evaluations")
    for i in range(3):
        evaluations.save(evaluation=evaluation(execution=False, comparison_id=str(i + 1) * 64))
    (tmp_path / "profile-sentinel.json").write_text('{"M42":{"target_hours":15,"hours":0}}')
    preserved = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")}
    candidate = composed_candidate(assessment(stage))
    service, gate = service_for(candidate)
    profile = {**valid_profile(), "projects": {"M42": {"hours": 0, "target_hours": 15}}}
    original_profile = deepcopy(profile)
    result = replace(service.evaluate(profile=profile, weather=object(), reference_time_utc=START,
                                     bortle=4, availability=AVAILABILITY, selected_project_id="M42"),
                     decision_id="synthetic-" + stage)
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    class Service:
        def evaluate(self, **kwargs):
            return result
    client = TestClient(create_app(service_factory=Service, profile_provider=lambda: profile,
        weather_provider=lambda *a: DEFAULT_WEATHER, clock=lambda: DEFAULT_WEATHER_REFERENCE_TIME,
        analysis_store_factory=lambda: store))
    response = client.post("/v1/tonight", json={"selected_project_id": "M42", "availability": {"mode": "all_night"}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actionability_refusal"]["refusal_stage"] == stage
    assert all((tmp_path / name).read_bytes() == raw for name, raw in preserved.items())
    before_restart = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")}
    def forbidden(*a, **k):
        raise AssertionError("Reading an archived analysis must not recalculate or authorize a mission")
    restarted = TestClient(create_app(service_factory=forbidden, profile_provider=forbidden,
        weather_provider=forbidden, analysis_store_factory=lambda: FileAnalysisHistory(store.directory)))
    reread = restarted.get("/v1/analysis-history/" + body["decision_id"])
    assert reread.status_code == 200, reread.text
    assert reread.json()["result"] == body
    import json, subprocess, sys
    from pathlib import Path
    script = "import json,sys; from astropilot.analysis_history import FileAnalysisHistory; print(json.dumps(FileAnalysisHistory(sys.argv[1]).load(sys.argv[2])))"
    child = subprocess.run([sys.executable, "-c", script, str(store.directory), body["decision_id"]],
                           cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, check=True)
    assert json.loads(child.stdout)["result"] == body
    assert restarted.get("/v1/analysis-history").json()["items"] == [reread.json()]
    assert before_restart == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert profile == original_profile and len(list((tmp_path / "field_observations").glob("*.json"))) == 3
    assert len(list((tmp_path / "outcome_evaluations").glob("*.json"))) == 3
    assert not (tmp_path / "execution_lineage").exists()
    gate.assert_not_called()
