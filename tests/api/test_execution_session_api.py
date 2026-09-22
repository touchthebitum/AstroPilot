"""Durable mission session reads and intent progress resume."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.execution_lineage_store import FileExecutionLineageStore
from astropilot.user_profile import load_user_profile, save_user_profile
from decision.mission.night_mission import NightMission
from decision.services.durable_tonight_application_service import DurableTonightApplicationService
import decision.services.intent_progress_credit as intent_credit_module


FIELD = "sh2-129_ou4"
HA = "sh2-129_ha"
OIII = "ou4_oiii"
START = datetime(2026, 9, 21, 20, tzinfo=timezone.utc)


class Acceptance:
    def __init__(self):
        self.context_store = self
        mission = NightMission(
            target="Sh2-129", confidence="HIGH", equipment=["samyang_183"],
            site_name="Buttes", window_start=START, window_end=START + timedelta(hours=4),
            mission_id="mission-ha", decision_id="decision-ha", selection_id="selection-ha",
            imaging_field_id=FIELD, acquisition_intent_id=HA,
        )
        self.missions = {"mission-ha": mission,
                         "mission-ha-other": replace(mission, mission_id="mission-ha-other",
                             decision_id="decision-ha-other", selection_id="selection-ha-other"),
                         "mission-oiii": replace(mission, mission_id="mission-oiii",
                             decision_id="decision-oiii", selection_id="selection-oiii",
                             acquisition_intent_id=OIII)}

    def load_mission(self, mission_id):
        return self.missions.get(mission_id)

    def load_selection(self, selection_id):
        mission = next((m for m in self.missions.values() if m.selection_id == selection_id), None)
        return SimpleNamespace(selection_id=selection_id, decision_id=mission.decision_id,
            selected_catalog_key="Sh2-129", selected_imaging_field_id=FIELD,
            selected_acquisition_intent_id=mission.acquisition_intent_id) if mission else None

    def latest_accepted_mission(self, **_kwargs):
        return None


def setup(tmp_path, monkeypatch, baseline=3600, target=True):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    acceptance = Acceptance()

    def client():
        def service():
            return DurableTonightApplicationService(
                application_service=object(), evidence_store=object(),
                decision_id_factory=lambda: "unused", acceptance_service=acceptance,
                execution_lineage_store=FileExecutionLineageStore(tmp_path / "execution_lineage"),
                profile_loader=load_user_profile, profile_saver=save_user_profile,
            )
        return TestClient(create_app(service_factory=service))

    api = client()
    assert api.put("/v1/configuration", json={
        "site": {"name": "Buttes", "latitude": 46.9, "longitude": 6.6, "bortle": 4},
        "equipment": {"preset_id": "samyang_183"},
        "projects": {"Sh2-129": {"hours": 2, "target_hours": 20, "importance": 9}},
    }).status_code == 200
    revision = load_user_profile()["profile_revision"]
    progress = api.put("/v1/projects/Sh2-129/progress", json={
        "expected_revision": revision, "imaging_field_id": FIELD,
        "acquisition_intent_progress": [{"acquisition_intent_id": HA,
            "acquired_duration_manual": baseline}],
        "acquisition_intent_targets": ([{"acquisition_intent_id": HA, "target_hours": 2}] if target else []),
    })
    assert progress.status_code == 200, progress.text
    return client


def create_completed(api, execution_id, mission_id="mission-ha", evidence_id=None, minutes=30):
    created = api.post("/v1/executions", json={"execution_id": execution_id, "mission_id": mission_id})
    assert created.status_code == 200, created.text
    started = api.post("/v1/execution-transitions", json={
        "execution_id": execution_id, "mission_id": mission_id, "status": "in_progress",
        "actual_start": START.isoformat(), "actual_end": None, "actual_duration": None,
    })
    assert started.status_code == 200, started.text
    completed = api.post("/v1/execution-transitions", json={
        "execution_id": execution_id, "mission_id": mission_id, "status": "completed",
        "actual_start": START.isoformat(), "actual_end": (START + timedelta(hours=1)).isoformat(),
        "actual_duration": 3600,
    })
    assert completed.status_code == 200, completed.text
    if evidence_id:
        recorded = api.post("/v1/outcome-evidence", json={
            "evidence_id": evidence_id, "execution_id": execution_id, "category": "acquisition",
            "observed_at": (START + timedelta(hours=1)).isoformat(), "source": "user",
            "usable_integration_duration": minutes * 60,
        })
        assert recorded.status_code == 200, recorded.text


def credit(api, execution_id, evidence_id, confirm=False, revision=None):
    return api.post(f"/v1/executions/{execution_id}/intent-progress-credit", json={
        "expected_revision": revision if revision is not None else load_user_profile()["profile_revision"],
        "evidence_ids": [evidence_id], "confirm_historical_baseline": confirm,
    })


def test_resume_each_stage_and_lost_responses(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch)
    api = fresh()
    assert api.get("/v1/accepted-mission/current").json() is None
    assert api.get("/v1/missions/mission-ha/executions").json() == []
    create_completed(api, "execution-1", evidence_id="evidence-1")
    session = fresh().get("/v1/executions/execution-1/session").json()
    assert session["execution"]["status"] == "completed"
    assert session["evidence"][0]["usable_integration_duration"] == 1800
    assert session["acquisition_intent_id"] == HA
    assert session["historical_baseline_seconds"] == 3600
    assert session["acquired_before_seconds"] == 3600
    assert session["credit"] is None
    assert credit(api, "execution-1", "evidence-1").json()["detail"]["code"] == "intent_progress_baseline_confirmation_required"
    assert credit(api, "execution-1", "evidence-1", confirm=True).status_code == 200
    after = fresh().get("/v1/executions/execution-1/session").json()
    assert after["acquired_before_seconds"] == 3600
    assert after["session_credit_seconds"] == 1800
    assert after["acquired_after_seconds"] == 5400
    assert after["remaining_hours"] == .5
    assert after["historical_baseline_confirmed"]
    assert len(fresh().get("/v1/execution-sessions").json()) == 1
    assert len(fresh().get("/v1/missions/mission-ha/executions").json()) == 1
    assert fresh().get("/v1/projects/Sh2-129/progress").json()["intent_progress_breakdown"][0]["effective_total_seconds"] == 5400
    assert credit(api, "execution-1", "evidence-1").json()["status"] == "already_applied"
    create_completed(fresh(), "execution-2", evidence_id="evidence-2", minutes=15)
    assert credit(fresh(), "execution-2", "evidence-2").status_code == 200
    second = fresh().get("/v1/executions/execution-2/session").json()
    assert second["acquired_before_seconds"] == 5400
    assert second["session_credit_seconds"] == 900
    assert second["acquired_after_seconds"] == 6300
    first_again = fresh().get("/v1/executions/execution-1/session").json()
    assert (first_again["acquired_before_seconds"], first_again["session_credit_seconds"],
            first_again["acquired_after_seconds"]) == (3600, 1800, 5400)
    assert first_again["current_acquired_seconds"] == 6300
    assert first_again["remaining_hours"] == .25  # Current, not historical.
    assert second["current_acquired_seconds"] == 6300
    assert fresh().get("/v1/projects/Sh2-129/progress").json()["intent_progress_breakdown"][0]["effective_total_seconds"] == 6300
    applied_at = first_again["credit"]["applied_at"]
    assert credit(fresh(), "execution-1", "evidence-1").json()["status"] == "already_applied"
    replayed = fresh().get("/v1/executions/execution-1/session").json()
    assert replayed["credit"]["applied_at"] == applied_at
    assert (replayed["acquired_before_seconds"], replayed["acquired_after_seconds"]) == (3600, 5400)
    changed = api.post("/v1/outcome-evidence", json={
        "evidence_id": "evidence-1", "execution_id": "execution-1", "category": "acquisition",
        "observed_at": (START + timedelta(hours=1)).isoformat(), "source": "user",
        "usable_integration_duration": 2400,
    })
    assert changed.status_code == 409
    assert fresh().get("/v1/executions/execution-1/session").json()["credit"] == after["credit"]


def test_other_intent_credit_does_not_change_historical_session(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch)
    api = fresh()
    create_completed(api, "execution-1", evidence_id="evidence-1")
    assert credit(api, "execution-1", "evidence-1", confirm=True).status_code == 200
    create_completed(api, "execution-oiii", mission_id="mission-oiii", evidence_id="evidence-oiii")
    assert credit(api, "execution-oiii", "evidence-oiii").status_code == 200
    first = fresh().get("/v1/executions/execution-1/session").json()
    assert (first["acquired_before_seconds"], first["acquired_after_seconds"],
            first["current_acquired_seconds"]) == (3600, 5400, 5400)


def test_equal_applied_at_orders_credits_by_execution_id_not_ledger_order(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch)
    api = fresh()
    # Credit the lexically later ID first, then set both timestamps equal.
    create_completed(api, "execution-z", evidence_id="evidence-z")
    assert credit(api, "execution-z", "evidence-z", confirm=True).status_code == 200
    create_completed(api, "execution-a", evidence_id="evidence-a", minutes=15)
    assert credit(api, "execution-a", "evidence-a").status_code == 200
    path = tmp_path / "user_profile.json"
    profile = json.loads(path.read_text())
    ledger = profile["intent_progress_credits"]
    ledger["execution-a"]["applied_at"] = ledger["execution-z"]["applied_at"]
    path.write_text(json.dumps(profile))
    first = fresh().get("/v1/executions/execution-a/session").json()
    second = fresh().get("/v1/executions/execution-z/session").json()
    assert (first["acquired_before_seconds"], first["acquired_after_seconds"]) == (3600, 4500)
    assert (second["acquired_before_seconds"], second["acquired_after_seconds"]) == (4500, 6300)
    assert first["current_acquired_seconds"] == second["current_acquired_seconds"] == 6300


def test_new_credit_keeps_append_chronology_when_clock_is_frozen(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch)
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return START.astimezone(tz)

    monkeypatch.setattr(intent_credit_module, "datetime", FrozenDatetime)
    api = fresh()
    create_completed(api, "execution-z", evidence_id="evidence-z")
    assert credit(api, "execution-z", "evidence-z", confirm=True).status_code == 200
    first = fresh().get("/v1/executions/execution-z/session").json()
    create_completed(api, "execution-a", evidence_id="evidence-a", minutes=15)
    assert credit(api, "execution-a", "evidence-a").status_code == 200
    second = fresh().get("/v1/executions/execution-a/session").json()
    reopened = fresh().get("/v1/executions/execution-z/session").json()
    assert datetime.fromisoformat(second["credit"]["applied_at"]) > datetime.fromisoformat(first["credit"]["applied_at"])
    assert (reopened["acquired_before_seconds"], reopened["acquired_after_seconds"]) == (3600, 5400)
    assert (second["acquired_before_seconds"], second["acquired_after_seconds"]) == (5400, 6300)


def test_second_execution_zero_baseline_missing_evidence_and_interruption(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch, baseline=0, target=False)
    api = fresh()
    create_completed(api, "execution-1", evidence_id="evidence-1")
    assert credit(api, "execution-1", "evidence-1").status_code == 200
    create_completed(api, "execution-2", evidence_id="evidence-2", minutes=15)
    assert credit(fresh(), "execution-2", "evidence-2").status_code == 200
    second = fresh().get("/v1/executions/execution-2/session").json()
    assert second["acquired_before_seconds"] == 1800
    assert second["session_credit_seconds"] == 900
    assert second["acquired_after_seconds"] == 2700
    assert second["target_hours"] is None and second["remaining_hours"] is None
    create_completed(api, "execution-3")
    assert credit(api, "execution-3", "missing").status_code == 422
    zero = api.post("/v1/outcome-evidence", json={
        "evidence_id": "evidence-zero", "execution_id": "execution-3", "category": "acquisition",
        "observed_at": START.isoformat(), "source": "user", "usable_integration_duration": 0,
    })
    assert zero.status_code == 200
    assert credit(api, "execution-3", "evidence-zero").status_code == 422
    absent = api.post("/v1/outcome-evidence", json={
        "evidence_id": "evidence-null", "execution_id": "execution-3", "category": "acquisition",
        "observed_at": START.isoformat(), "source": "user", "usable_integration_duration": None,
    })
    assert absent.status_code == 200
    assert credit(api, "execution-3", "evidence-null").status_code == 422
    read = fresh().get("/v1/executions/execution-3/session")
    assert read.status_code == 200
    assert read.json()["session_credit_seconds"] == 0
    assert api.post("/v1/executions", json={"execution_id": "interrupted", "mission_id": "mission-ha"}).status_code == 200
    assert api.post("/v1/execution-transitions", json={"execution_id": "interrupted", "mission_id": "mission-ha",
        "status": "in_progress", "actual_start": START.isoformat(), "actual_end": None, "actual_duration": None}).status_code == 200
    assert api.post("/v1/execution-transitions", json={"execution_id": "interrupted", "mission_id": "mission-ha",
        "status": "interrupted", "actual_start": START.isoformat(),
        "actual_end": (START + timedelta(hours=1)).isoformat(), "actual_duration": 3600}).status_code == 200
    assert credit(api, "interrupted", "evidence-1").status_code == 422
    assert fresh().get("/v1/executions/interrupted/session").json()["credit"] is None


def test_mission_intent_is_exact_and_revision_conflict_reads_canonical(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch)
    api = fresh()
    create_completed(api, "execution-oiii", mission_id="mission-oiii", evidence_id="evidence-oiii")
    before = load_user_profile()["profile_revision"]
    assert credit(api, "execution-oiii", "evidence-oiii").status_code == 200
    assert credit(api, "execution-oiii", "evidence-oiii", revision=before).status_code == 409
    state = fresh().get("/v1/executions/execution-oiii/session").json()
    assert state["acquisition_intent_id"] == OIII
    assert state["acquired_after_seconds"] == 1800
    assert fresh().get("/v1/missions/mission-ha/executions").json() == []
    assert fresh().get("/v1/missions/mission-oiii/executions").json()[0]["credit"]["acquisition_intent_id"] == OIII


def test_read_after_each_write_and_concurrent_commands(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch, baseline=0)
    api = fresh()
    body = {"execution_id": "concurrent", "mission_id": "mission-ha"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(pool.map(lambda _: fresh().post("/v1/executions", json=body), range(2)))
    assert all(response.status_code == 200 for response in created)
    assert fresh().get("/v1/executions/concurrent/session").json()["execution"]["status"] == "not_started"
    start = {**body, "status": "in_progress", "actual_start": START.isoformat(),
             "actual_end": None, "actual_duration": None}
    with ThreadPoolExecutor(max_workers=2) as pool:
        started = list(pool.map(lambda _: fresh().post("/v1/execution-transitions", json=start), range(2)))
    assert sorted(response.status_code for response in started) == [200, 409]
    assert fresh().get("/v1/executions/concurrent/session").json()["execution"]["status"] == "in_progress"
    end = {**body, "status": "completed", "actual_start": START.isoformat(),
           "actual_end": (START + timedelta(hours=1)).isoformat(), "actual_duration": 3600}
    assert api.post("/v1/execution-transitions", json=end).status_code == 200
    assert fresh().get("/v1/executions/concurrent/session").json()["execution"]["status"] == "completed"
    evidence = {"evidence_id": "concurrent-evidence", "execution_id": "concurrent",
                "category": "acquisition", "observed_at": START.isoformat(),
                "source": "user", "usable_integration_duration": 1800}
    with ThreadPoolExecutor(max_workers=2) as pool:
        recorded = list(pool.map(lambda _: fresh().post("/v1/outcome-evidence", json=evidence), range(2)))
    assert all(response.status_code == 200 for response in recorded)
    assert len(fresh().get("/v1/executions/concurrent/session").json()["evidence"]) == 1
    revision = load_user_profile()["profile_revision"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        credited = list(pool.map(lambda _: credit(fresh(), "concurrent", "concurrent-evidence", revision=revision), range(2)))
    assert sorted(response.status_code for response in credited) == [200, 409]
    state = fresh().get("/v1/executions/concurrent/session").json()
    assert state["session_credit_seconds"] == 1800
    assert state["acquired_after_seconds"] == 1800


@pytest.mark.parametrize("change", ["intent", "mission_selection", "evidence", "duration"])
def test_session_read_rejects_structurally_valid_wrong_credit(tmp_path, monkeypatch, change):
    fresh = setup(tmp_path, monkeypatch, baseline=0)
    api = fresh()
    create_completed(api, "execution-1", evidence_id="evidence-1")
    assert credit(api, "execution-1", "evidence-1").status_code == 200
    path = tmp_path / "user_profile.json"
    profile = json.loads(path.read_text())
    entry = profile["intent_progress_credits"]["execution-1"]
    if change == "intent":
        entry["acquisition_intent_id"] = OIII
    elif change == "mission_selection":
        entry["mission_id"] = "mission-ha-other"
        entry["selection_id"] = "selection-ha-other"
        entry["decision_id"] = "decision-ha-other"
    elif change == "evidence":
        entry["evidence_ids"] = ["other-evidence"]
    else:
        entry["usable_durations_us"] = [900_000_000]
        entry["total_duration_us"] = 900_000_000
    path.write_text(json.dumps(profile))
    response = fresh().get("/v1/executions/execution-1/session")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "session_credit_inconsistent"


@pytest.mark.parametrize("same_intent", [True, False])
def test_session_read_validates_only_contributing_credits(tmp_path, monkeypatch, same_intent):
    fresh = setup(tmp_path, monkeypatch, baseline=0)
    api = fresh()
    create_completed(api, "execution-1", evidence_id="evidence-1")
    assert credit(api, "execution-1", "evidence-1").status_code == 200
    mission_id = "mission-ha" if same_intent else "mission-oiii"
    create_completed(api, "execution-2", mission_id=mission_id, evidence_id="evidence-2")
    assert credit(api, "execution-2", "evidence-2").status_code == 200

    path = tmp_path / "user_profile.json"
    profile = json.loads(path.read_text())
    entry = profile["intent_progress_credits"]["execution-2"]
    entry.update(mission_id="mission-ha-other", selection_id="selection-ha-other",
                 decision_id="decision-ha-other")
    path.write_text(json.dumps(profile))

    response = fresh().get("/v1/executions/execution-1/session")
    if same_intent:
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "session_credit_inconsistent"
    else:
        assert response.status_code == 200
        assert response.json()["acquired_before_seconds"] == 0
        assert fresh().get("/v1/executions/execution-2/session").status_code == 503


def test_session_read_normalizes_corrupt_contributing_execution(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch, baseline=0)
    api = fresh()
    create_completed(api, "execution-1", evidence_id="evidence-1")
    assert credit(api, "execution-1", "evidence-1").status_code == 200
    create_completed(api, "execution-2", evidence_id="evidence-2")
    assert credit(api, "execution-2", "evidence-2").status_code == 200

    (tmp_path / "execution_lineage" / "execution-2.json").write_text("invalid json")

    response = fresh().get("/v1/executions/execution-1/session")
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "session_credit_inconsistent"}}

    direct = fresh().get("/v1/executions/execution-2/session")
    assert direct.status_code == 503
    assert direct.json() == {"detail": {"code": "invalid_json_document"}}


def test_session_discovery_orders_missions_by_persisted_chronology(tmp_path, monkeypatch):
    fresh = setup(tmp_path, monkeypatch, baseline=0)
    api = fresh()
    assert api.post("/v1/executions", json={"execution_id": "z-old", "mission_id": "mission-ha"}).status_code == 200
    assert api.post("/v1/executions", json={"execution_id": "a-new", "mission_id": "mission-oiii"}).status_code == 200
    assert api.post("/v1/execution-transitions", json={
        "execution_id": "a-new", "mission_id": "mission-oiii", "status": "in_progress",
        "actual_start": (START + timedelta(days=1)).isoformat(),
        "actual_end": None, "actual_duration": None,
    }).status_code == 200
    sessions = fresh().get("/v1/execution-sessions").json()
    assert {item["mission_id"] for item in sessions} == {"mission-ha", "mission-oiii"}
    assert [item["execution"]["execution_id"] for item in sessions] == ["a-new", "z-old"]
    assert sessions[0]["chronology_at"] == (START + timedelta(days=1)).isoformat()
    assert all(item["mission"]["target"] == "Sh2-129" for item in sessions)
