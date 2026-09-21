import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from astropilot.app import create_app
from astropilot.user_profile import UserProfileError, get_user_data_dir, load_user_profile, save_user_profile
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import AcquisitionOutcomeEvidence, OutcomeEvidenceCategory, OutcomeEvidenceSource
from decision.services.intent_progress_credit import apply_execution_credit


PROJECT = {"hours": 2, "target_hours": 20, "importance": 9}
HA = "sh2-129_ha"
OIII = "ou4_oiii"
FIELD = "sh2-129_ou4"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    client = TestClient(create_app())
    response = client.put("/v1/configuration", json={
        "site": {"name": "Buttes", "latitude": 46.9, "longitude": 6.6, "bortle": 4},
        "equipment": {"preset_id": "samyang_183"},
        "projects": {"Sh2-129": PROJECT},
    })
    assert response.status_code == 200, response.text
    return client


def path():
    return "/v1/projects/Sh2-129/progress"


def put(client, **fields):
    revision = client.get(path()).json()["profile_revision"]
    return client.put(path(), json={"expected_revision": revision, **fields})


def detailed(intent, frames, seconds=300):
    return {"acquisition_intent_id": intent, "acquired_frames": frames,
            "exposure_seconds": seconds}


def test_execution_credit_endpoint_projection_baseline_and_editor_guard(client):
    put(client, imaging_field_id=FIELD,
        acquisition_intent_progress=[{"acquisition_intent_id": OIII, "acquired_duration_manual": 3600}],
        acquisition_intent_targets=[{"acquisition_intent_id": OIII, "target_hours": 2}])
    start = datetime(2026, 9, 21, 20, tzinfo=timezone.utc)
    mission = SimpleNamespace(mission_id="mission-1", decision_id="decision-1",
                              selection_id="selection-1", imaging_field_id=FIELD,
                              acquisition_intent_id=OIII, target="Sh2-129")
    selection = SimpleNamespace(selection_id="selection-1", decision_id="decision-1",
                                selected_catalog_key="Sh2-129", selected_imaging_field_id=FIELD,
                                selected_acquisition_intent_id=OIII)
    executions = {key: Execution(key, "mission-1", ExecutionStatus.COMPLETED,
        start, start + timedelta(hours=3), timedelta(hours=3))
        for key in ("execution-1", "execution-2")}
    evidence = {key: AcquisitionOutcomeEvidence(key, execution_id,
        OutcomeEvidenceCategory.ACQUISITION, start, OutcomeEvidenceSource.USER,
        actual_capture_duration=timedelta(hours=3), usable_integration_duration=duration)
        for key, execution_id, duration in (
            ("evidence-1", "execution-1", timedelta(minutes=30)),
            ("evidence-2", "execution-2", timedelta(minutes=15)))}

    def apply(**kwargs):
        return apply_execution_credit(profile=load_user_profile(),
            load_execution=executions.get, load_mission=lambda _: mission,
            load_selection=lambda _: selection, load_evidence=evidence.get,
            save_profile=save_user_profile, **kwargs)

    api = TestClient(create_app(service_factory=lambda: SimpleNamespace(apply_intent_progress_credit=apply)))
    url = "/v1/executions/execution-1/intent-progress-credit"
    revision = load_user_profile()["profile_revision"]
    body = {"expected_revision": revision, "evidence_ids": ["evidence-1"]}
    refused = api.post(url, json=body)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "intent_progress_baseline_confirmation_required"
    assert load_user_profile()["profile_revision"] == revision
    applied = api.post(url, json={**body, "confirm_historical_baseline": True})
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied" and applied.json()["total_duration_us"] == 1_800_000_000
    marker = json.loads(json.dumps(load_user_profile()["intent_progress_baselines"]["Sh2-129"][OIII]))
    second_url = "/v1/executions/execution-2/intent-progress-credit"
    second_body = {"expected_revision": revision + 1, "evidence_ids": ["evidence-2"]}
    second = api.post(second_url, json=second_body)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "applied" and second.json()["total_duration_us"] == 900_000_000
    assert load_user_profile()["intent_progress_baselines"]["Sh2-129"][OIII] == marker
    assert api.post(second_url, json={**second_body, "expected_revision": revision + 2,
        "confirm_historical_baseline": True}).json()["status"] == "already_applied"
    replay = api.post(url, json={**body, "expected_revision": revision + 2})
    assert replay.status_code == 200 and replay.json()["status"] == "already_applied"
    stale = api.post(url, json=body)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "profile_revision_conflict"
    projection = api.get(path()).json()
    breakdown = next(item for item in projection["intent_progress_breakdown"] if item["acquisition_intent_id"] == OIII)
    assert breakdown == {"acquisition_intent_id": OIII, "base_seconds": 3600,
                         "credits_us": 2_700_000_000, "effective_total_seconds": 6300,
                         "remaining_hours": 0.25}
    derived = next(item for item in projection["acquisition_intent_remaining_progress"]
                   if item["acquisition_intent_id"] == OIII)
    assert derived["acquired_seconds"] == 6300 and derived["remaining_hours"] == 0.25
    assert api.put(path(), json={"expected_revision": revision + 2,
        "acquisition_intent_progress": []}).json()["detail"]["code"] == "intent_progress_baseline_invalid"
    changed = api.put(path(), json={"expected_revision": revision + 2,
        "imaging_field_id": "ic1396"})
    assert changed.status_code == 409
    assert load_user_profile()["projects"]["Sh2-129"]["hours"] == 2
    assert load_user_profile()["projects"]["Sh2-129"]["target_hours"] == 20
    assert load_user_profile()["intent_progress_baselines"]["Sh2-129"][OIII] == marker


def test_duplicate_credit_json_key_fails_closed(client):
    put(client, imaging_field_id=FIELD)
    profile_path = get_user_data_dir() / "user_profile.json"
    document = profile_path.read_text()
    # Duplicate JSON object keys cannot be collapsed into a single credit.
    document = document.replace('"profile_revision": 2', '"profile_revision": 2, "profile_revision": 2')
    profile_path.write_text(document)
    assert client.get(path()).status_code == 503


def test_credit_api_distinguishes_candidate_conflict_from_corrupt_configuration(client):
    def reject_credit(**kwargs):
        raise UserProfileError("intent_progress_baseline_immutable")

    api = TestClient(create_app(service_factory=lambda: SimpleNamespace(
        apply_intent_progress_credit=reject_credit)))
    url = "/v1/executions/execution-2/intent-progress-credit"
    body = {"expected_revision": load_user_profile()["profile_revision"],
            "evidence_ids": ["evidence-2"]}
    conflict = api.post(url, json=body)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "intent_progress_baseline_immutable"

    (get_user_data_dir() / "user_profile.json").write_text("{invalid json")
    corrupt = api.post(url, json=body)
    assert corrupt.status_code == 503
    assert corrupt.json()["detail"]["code"] == "configuration_corrupt"


def test_derived_read_only_projection_after_save(client):
    targets = [{"acquisition_intent_id": HA, "target_hours": 2}]
    saved = put(client, imaging_field_id=FIELD, acquisition_intent_targets=targets,
                acquisition_intent_progress=[detailed(HA, 24)])
    assert saved.status_code == 200, saved.text
    item, unknown = saved.json()["acquisition_intent_remaining_progress"]
    assert item == {"acquisition_intent_id": HA, "acquired_seconds": 7200,
                    "acquired_hours": 2, "target_hours": 2, "remaining_hours": 0}
    assert unknown["acquired_hours"] is None and unknown["remaining_hours"] is None
    assert client.get(path()).json()["acquisition_intent_remaining_progress"] == [item, unknown]
    assert "acquisition_intent_remaining_progress" not in load_user_profile()["projects"]["Sh2-129"]


def test_detailed_round_trip_and_legacy_hours_unchanged(client):
    entries = [detailed(HA, 159), detailed(OIII, 43)]
    saved = put(client, imaging_field_id=FIELD, acquisition_intent_progress=entries)
    assert saved.status_code == 200, saved.text
    assert saved.json()["acquisition_intent_progress"] == entries
    assert 159 * 300 == 13 * 3600 + 15 * 60
    assert 43 * 300 == 3 * 3600 + 35 * 60
    assert client.get(path()).json()["acquisition_intent_progress"] == entries
    assert load_user_profile()["projects"]["Sh2-129"]["hours"] == 2
    assert load_user_profile()["projects"]["Sh2-129"]["target_hours"] == 20


def test_extreme_finite_product_is_projected_without_persisting_derivation(client):
    entry = detailed(HA, 10**309, 1e-310)
    saved = put(client, imaging_field_id=FIELD, acquisition_intent_progress=[entry],
                acquisition_intent_targets=[{"acquisition_intent_id": HA, "target_hours": 2}])
    assert saved.status_code == 200, saved.text
    projected = saved.json()["acquisition_intent_remaining_progress"][0]
    assert math.isclose(projected["acquired_seconds"], 0.1, rel_tol=1e-12)
    assert projected["remaining_hours"] == 2 - projected["acquired_hours"]
    assert client.get(path()).json()["acquisition_intent_remaining_progress"][0] == projected
    persisted = load_user_profile()["projects"]["Sh2-129"]
    assert persisted["acquisition_intent_progress"] == [entry]
    assert "acquisition_intent_remaining_progress" not in persisted


def test_manual_unknown_zero_clear_and_optional_target(client):
    initial = client.get(path()).json()
    assert initial["imaging_field_id"] is None
    assert initial["acquisition_intent_progress"] == []
    manual = [{"acquisition_intent_id": HA, "acquired_duration_manual": 47700}]
    saved = put(client, imaging_field_id=FIELD, acquisition_intent_progress=manual)
    assert saved.status_code == 200, saved.text
    assert saved.json()["acquisition_intent_targets"] == []
    assert saved.json()["acquisition_intent_progress"] == manual
    zero = [detailed(HA, 0)]
    assert put(client, acquisition_intent_progress=zero).status_code == 200
    assert client.get(path()).json()["acquisition_intent_progress"] == zero
    assert put(client, acquisition_intent_progress=[]).status_code == 200
    assert client.get(path()).json()["acquisition_intent_progress"] == []


@pytest.mark.parametrize("entries", [
    [dict(detailed(HA, 1), acquired_duration_manual=300)],
    [{"acquisition_intent_id": HA, "acquired_frames": 1}],
    [{"acquisition_intent_id": HA, "exposure_seconds": 300}],
    [detailed(HA, -1)],
    [detailed(HA, 1.5)],
    [detailed(HA, True)],
    [detailed(HA, 1, 0)],
    [detailed(HA, 1, -1)],
    [detailed(HA, 1, float("inf"))],
    [detailed(HA, 10**10, 1e308)],
    [detailed(HA, 10**400, 1.0)],
    [{"acquisition_intent_id": HA, "acquired_duration_manual": 10**400}],
    [{"acquisition_intent_id": HA, "acquired_duration_manual": -1}],
    [{"acquisition_intent_id": HA, "acquired_duration_manual": float("nan")}],
    [detailed(HA, 1), detailed(HA, 2)],
    [detailed("foreign_intent", 1)],
])
def test_invalid_progress_is_422_and_does_not_write(client, entries):
    before = load_user_profile()
    revision = client.get(path()).json()["profile_revision"]
    response = client.put(path(), content=json.dumps({
        "expected_revision": revision, "imaging_field_id": FIELD,
        "acquisition_intent_progress": entries,
    }), headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert load_user_profile() == before


def test_targets_replace_or_preserve_and_revision_conflict(client):
    targets = [{"acquisition_intent_id": HA, "target_hours": 15}]
    saved = put(client, imaging_field_id=FIELD, acquisition_intent_targets=targets)
    assert saved.status_code == 200
    revision = saved.json()["profile_revision"]
    assert put(client, acquisition_intent_progress=[detailed(HA, 2)]).status_code == 200
    assert client.get(path()).json()["acquisition_intent_targets"] == targets
    stale = client.put(path(), json={"expected_revision": revision,
                                    "acquisition_intent_targets": []})
    assert stale.status_code == 409
    assert client.get(path()).json()["acquisition_intent_targets"] == targets
    assert put(client, acquisition_intent_targets=[]).status_code == 200
    assert client.get(path()).json()["acquisition_intent_targets"] == []


def test_missing_project_and_missing_revision(client):
    assert client.get("/v1/projects/missing/progress").status_code == 404
    assert client.put("/v1/projects/missing/progress", json={"expected_revision": 1}).status_code == 404
    assert client.put(path(), json={"acquisition_intent_progress": []}).status_code == 422


def test_corrupt_profile_put_matches_get_and_does_not_write(client, tmp_path):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("{invalid json", encoding="utf-8")
    before = profile_path.read_bytes()
    expected = {"detail": {"code": "configuration_corrupt"}}
    assert client.get(path()).status_code == 503
    response = client.put(path(), json={"expected_revision": 1,
                                       "acquisition_intent_progress": []})
    assert response.status_code == 503
    assert response.json() == expected
    assert profile_path.read_bytes() == before


def test_configuration_round_trip_preserves_progress(client):
    progress = [detailed(HA, 159), {"acquisition_intent_id": OIII,
                                    "acquired_duration_manual": 12900}]
    assert put(client, imaging_field_id=FIELD, acquisition_intent_progress=progress).status_code == 200
    configuration = client.get("/v1/configuration").json()
    assert configuration["projects"]["Sh2-129"]["acquisition_intent_progress"] == progress
    update = {
        "site": {key: configuration["site"][key] for key in ("name", "latitude", "longitude", "bortle")},
        "equipment": {"preset_id": "samyang_183"},
        "projects": configuration["projects"],
        "expected_revision": configuration["profile_revision"],
    }
    assert client.put("/v1/configuration", json=update).status_code == 200
    assert client.get(path()).json()["acquisition_intent_progress"] == progress
    update["expected_revision"] += 1
    update["projects"]["Sh2-129"].pop("acquisition_intent_progress")
    assert client.put("/v1/configuration", json=update).status_code == 200
    assert client.get(path()).json()["acquisition_intent_progress"] == progress


def test_configuration_rejects_invalid_progress_without_writing(client):
    configuration = client.get("/v1/configuration").json()
    before = load_user_profile()
    response = client.put("/v1/configuration", json={
        "site": {key: configuration["site"][key] for key in ("name", "latitude", "longitude", "bortle")},
        "equipment": {"preset_id": "samyang_183"},
        "projects": {"Sh2-129": {**PROJECT, "imaging_field_id": FIELD,
                                    "acquisition_intent_progress": [detailed("foreign_intent", 1)]}},
        "expected_revision": configuration["profile_revision"],
    })
    assert response.status_code == 422
    assert load_user_profile() == before


def test_field_change_rejects_incoherent_retained_intents(client, monkeypatch):
    assert put(client, imaging_field_id=FIELD,
               acquisition_intent_progress=[detailed(HA, 1)]).status_code == 200
    before = load_user_profile()
    # A second field with a distinct intent makes the retained-ID rule observable.
    from decision.models.imaging_field import ImagingFieldDefinition, ImagingFieldComponent, AcquisitionIntent
    import astropilot.app as app_module
    import astropilot.user_profile as profile_module
    from decision.services.imaging_field_resolver import ImagingFieldResolver
    from decision.definitions.production_imaging_fields import CELESTIAL_OBJECT_DEFINITIONS, IMAGING_FIELD_DEFINITIONS
    other = ImagingFieldDefinition("other_field", "Other", (ImagingFieldComponent("ou4"),),
                                   (AcquisitionIntent("other_intent", "Ha", ("ou4",)),))
    monkeypatch.setattr(app_module, "IMAGING_FIELD_DEFINITIONS", (*IMAGING_FIELD_DEFINITIONS, other))
    monkeypatch.setattr(profile_module, "build_production_imaging_field_resolver",
                        lambda: ImagingFieldResolver((*IMAGING_FIELD_DEFINITIONS, other), CELESTIAL_OBJECT_DEFINITIONS))
    response = put(client, imaging_field_id="other_field")
    assert response.status_code == 422
    assert load_user_profile() == before
    response = put(client, imaging_field_id="other_field", acquisition_intent_progress=[])
    assert response.status_code == 200, response.text


def test_historical_profile_get_does_not_migrate_or_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    destination = tmp_path / "user_profile.json"
    shutil.copyfile(Path(__file__).resolve().parents[2] / "data/user_profile.json", destination)
    before = destination.read_bytes()
    client = TestClient(create_app())
    response = client.get(path())
    assert response.status_code == 200
    assert response.json()["imaging_field_id"] is None
    assert response.json()["acquisition_intent_progress"] == []
    assert destination.read_bytes() == before
