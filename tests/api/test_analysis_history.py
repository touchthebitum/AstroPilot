"""Read-only synthetic regressions for refused sessions and durable analysis."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import pytest

from astropilot.analysis_history import FileAnalysisHistory, AnalysisHistoryError
from astropilot.app import create_app
from decision.forecast.target_refusal import missing_target_refusal
from decision.services.tonight_application_service import TonightResult, TonightStatus
from test_profile_backup import source
from test_tonight_api import valid_profile, DEFAULT_WEATHER, DEFAULT_WEATHER_REFERENCE_TIME

SHA_ID = "refused-M42"
ZONE = ZoneInfo("Europe/Zurich")


def refusal():
    return {"catalog_key": "M42", "code": "target_below_minimum_altitude",
            "minimum_altitude_deg": 30, "sample_count": 3,
            "window_start": "2026-10-25T21:00:00+01:00",
            "window_end": "2026-10-25T22:30:00+01:00"}


def payload():
    return {"status": "no_candidate", "decision_id": SHA_ID, "target_refusal": refusal()}


def save(store, key=SHA_ID, created=None):
    body = {**payload(), "decision_id": key}
    store.save(key=key, created_at=created or DEFAULT_WEATHER_REFERENCE_TIME,
               request={"selected_project_id": "M42", "availability": {"mode": "all_night"}}, result=body)


def test_actual_M42_early_window_altitude_and_unknown_cause():
    from astropilot.engines.sky_engine import SkyEngine
    from astropilot.catalog import CATALOG
    from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
    availability = SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
        start=datetime(2026, 10, 25, 21, tzinfo=ZONE),
        end=datetime(2026, 10, 25, 22, 30, tzinfo=ZONE))
    hours = [{"time": datetime(2026, 10, 25, h, tzinfo=ZONE)} for h in (20, 21, 22, 23)]
    result = missing_target_refusal(sky=SkyEngine(), hours=hours, target=CATALOG["M42"],
        catalog_key="M42", profile={"preferences": {}}, availability=availability, lat=46.75, lon=6.55)
    assert result["code"] == "target_below_minimum_altitude"
    assert result["minimum_altitude_deg"] == 30 and result["sample_count"] > 0
    # No visibility samples is not proof of a bad sky or low altitude.
    empty = missing_target_refusal(sky=SkyEngine(), hours=[], target=CATALOG["M42"],
        catalog_key="M42", profile={"preferences": {}}, availability=availability, lat=46.75, lon=6.55)
    assert empty["code"] == "target_window_unavailable"


def test_live_refusal_is_archived_and_read_after_app_restart_without_side_effects(tmp_path):
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    profile = valid_profile()
    profile.setdefault("projects", {})["M42"] = {"hours": 0, "target_hours": 15}
    class Service:
        def evaluate(self, **kwargs):
            return TonightResult({"date": "2026-10-25", "target_refusals": {"M42": refusal()}},
                                 None, None, TonightStatus.NO_CANDIDATE, decision_id=SHA_ID)
    client = TestClient(create_app(service_factory=Service, profile_provider=lambda: profile,
        weather_provider=lambda *a: DEFAULT_WEATHER, clock=lambda: DEFAULT_WEATHER_REFERENCE_TIME,
        analysis_store_factory=lambda: store))
    result = client.post("/v1/tonight", json={"selected_project_id": "M42", "availability": {"mode": "all_night"}})
    assert result.status_code == 200, result.text
    assert result.json()["target_refusal"] == refusal()
    before = {p.name: p.read_bytes() for p in store.directory.iterdir() if p.is_file()}
    def forbidden(*args, **kwargs):
        raise AssertionError("An archived analysis must not evaluate weather, load a project or authorize a mission")
    restarted = TestClient(create_app(service_factory=forbidden, profile_provider=forbidden,
        weather_provider=forbidden, analysis_store_factory=lambda: FileAnalysisHistory(store.directory)))
    record = restarted.get("/v1/analysis-history/" + SHA_ID)
    assert record.status_code == 200, record.text
    assert record.headers["cache-control"] == "no-store"
    assert record.json()["result"]["target_refusal"] == refusal()
    assert record.json()["request"]["selected_project_id"] == "M42"
    assert restarted.get("/v1/analysis-history").json()["items"] == [record.json()]
    assert {p.name: p.read_bytes() for p in store.directory.iterdir() if p.is_file()} == before
    assert restarted.get("/v1/analysis-history/not-archived").status_code == 404


def test_reading_empty_history_creates_nothing(tmp_path):
    root = tmp_path / "not-created"
    store = FileAnalysisHistory(root)
    assert store.list_records() == {"items": [], "next_before": None}
    assert store.load("missing") is None
    assert not root.exists()


def test_history_is_immutable_bounded_paginated_and_fails_closed(tmp_path, monkeypatch):
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    save(store, "first")
    save(store, "second", DEFAULT_WEATHER_REFERENCE_TIME + timedelta(minutes=1))
    first_page = store.list_records(limit=1)
    assert first_page["items"][0]["decision_id"] == "second"
    assert first_page["next_before"] == "second"
    assert store.list_records(before="second", limit=1)["items"][0]["decision_id"] == "first"
    original = (store.directory / "first.json").read_bytes()
    with pytest.raises(AnalysisHistoryError, match="conflict"):
        save(store, "first", DEFAULT_WEATHER_REFERENCE_TIME + timedelta(minutes=2))
    assert (store.directory / "first.json").read_bytes() == original
    with pytest.raises(AnalysisHistoryError):
        store.load("../outside")
    (store.directory / "second.json").write_bytes(b'{"broken":true}')
    with pytest.raises(AnalysisHistoryError, match="invalid"):
        store.list_records()


@pytest.mark.parametrize("claim_alert", [False, True])
def test_archive_write_failure_is_visible(tmp_path, monkeypatch, claim_alert):
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    profile = valid_profile()
    class Service:
        def evaluate(self, **kwargs):
            return TonightResult({"date": "2026-10-25"}, None, None,
                                 TonightStatus.NO_CANDIDATE, decision_id=SHA_ID)
    def full_disk(**kwargs):
        raise OSError("synthetic disk full")
    monkeypatch.setattr(store, "save", full_disk)
    client = TestClient(create_app(service_factory=Service, profile_provider=lambda: profile,
        weather_provider=lambda *a: DEFAULT_WEATHER, clock=lambda: DEFAULT_WEATHER_REFERENCE_TIME,
        analysis_store_factory=lambda: store))
    response = client.post("/v1/tonight", json={"availability": {"mode": "all_night"}, "claim_opportunity_alert": claim_alert})
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "analysis_history_unavailable"}}


def test_analyses_are_included_in_profile_backup_and_restore(source, tmp_path):
    from astropilot.profile_backup import create_backup, inspect_backup, restore_empty, snapshot
    store = FileAnalysisHistory(source / "analysis_history")
    save(store)
    before = snapshot(source)
    raw, summary = create_backup(source)
    files, _ = inspect_backup(raw)
    assert files == before and "analysis_history/refused-M42.json" in files
    destination = tmp_path / "restored"
    restore_empty(destination, files)
    assert FileAnalysisHistory(destination / "analysis_history").load(SHA_ID) == store.load(SHA_ID)
    assert snapshot(source) == before


def test_invalid_history_blocks_backup_instead_of_dropping_it(source):
    from astropilot.profile_backup import BackupError, create_backup
    root = source / "analysis_history"
    root.mkdir()
    (root / "broken.json").write_bytes(b'{"broken":true}')
    with pytest.raises(BackupError):
        create_backup(source)


def test_archive_rejects_duplicate_fields_nonfinite_and_links(tmp_path):
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    save(store)
    path = store.directory / (SHA_ID + ".json")
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"schema":', b'"schema":"duplicate","schema":', 1))
    with pytest.raises(AnalysisHistoryError):
        store.load(SHA_ID)
    path.write_bytes(raw.replace(b'30', b'NaN', 1))
    with pytest.raises(AnalysisHistoryError):
        store.load(SHA_ID)
    path.write_bytes(raw)
    # Native hard-link check also runs where symlink creation is not available.
    import os
    os.link(path, store.directory / "alias.json")
    with pytest.raises(AnalysisHistoryError):
        store.load(SHA_ID)


def test_forecast_keeps_an_excluded_target_in_diagnostics():
    from types import SimpleNamespace
    from astropilot.engines.sky_engine import SkyEngine
    from astropilot.catalog import CATALOG
    import astro_score
    from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
    from astral import LocationInfo
    availability = SessionAvailability(SessionAvailabilityMode.FIXED_WINDOW,
        start=datetime(2026, 10, 25, 21, tzinfo=ZONE),
        end=datetime(2026, 10, 25, 22, 30, tzinfo=ZONE))
    profile = {"location": {"name": "synthetic", "latitude": 46.75, "longitude": 6.55},
        "active_equipment": "samyang_183", "available_equipment": ["samyang_183"], "preferences": {}}
    refusals = {}
    engine = astro_score.forecast_engine
    from copy import copy
    engine = copy(engine)
    engine.target_objects = {"M42": CATALOG["M42"]}
    hours = [{"time": datetime(2026, 10, 25, h, tzinfo=ZONE)} for h in (20, 21, 22, 23)]
    results = engine.evaluate_targets(sky=SkyEngine(), hours=hours, weather=None, illumination=50,
        moon_rise=None, moon_set=None, city_info=LocationInfo("synthetic", "", "Europe/Zurich", 46.75, 6.55),
        lat=46.75, lon=6.55, bortle=4, target="deep_sky", profile=profile,
        decision_engine=SimpleNamespace(), availability=availability, target_refusals=refusals)
    assert results == []
    assert refusals["M42"]["code"] == "target_below_minimum_altitude"
    night = astro_score.build_forecast_result(night_date="2026-10-25", night_evaluation=None,
        night_context={"hours": hours}, bortle=4, target_refusals=refusals)
    assert night["top_objects"] == [] and night["target_refusals"] == refusals


def test_visibility_does_not_guess_altitude_when_samples_are_high():
    from astropilot.engines.sky_engine import SkyEngine
    from astropilot.catalog import CATALOG
    sky = SkyEngine()
    hours = [{"time": datetime(2026, 10, 26, h, tzinfo=ZONE)} for h in (2, 3, 4)]
    result = missing_target_refusal(sky=sky, hours=hours, target=CATALOG["M42"],
        catalog_key="M42", profile={"preferences": {}}, availability=None, lat=46.75, lon=6.55)
    assert result["code"] == "target_window_unavailable"


def test_production_pipeline_M42_refusal_and_restart(tmp_path, monkeypatch):
    from dataclasses import replace
    from astropilot.user_profile import save_user_profile
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    profile = valid_profile()
    profile["projects"] = {"M42": {"hours": 0, "target_hours": 15, "imaging_field_id": "m42",
        "acquisition_intent_targets": [{"acquisition_intent_id": "m42_ha", "target_hours": 15}],
        "acquisition_intent_progress": [{"acquisition_intent_id": "m42_ha", "acquired_duration_manual": 0}]}}
    save_user_profile(profile)
    # Three synthetic historical records are never read or rewritten by analysis.
    old = tmp_path / "field_observations"
    old.mkdir()
    for i in range(3):
        (old / (str(i) + ".json")).write_text(json.dumps({"synthetic_sentinel": i}))
    before = {p.name: p.read_bytes() for p in old.iterdir()}
    reference = datetime(2026, 10, 25, 19, 50, tzinfo=timezone.utc)
    start = datetime(2026, 10, 25, tzinfo=timezone.utc)
    times = [start + timedelta(hours=i) for i in range(72)]
    values = {"cloud_cover": 70, "cloud_cover_low": 70, "cloud_cover_mid": 70, "cloud_cover_high": 70,
              "precipitation": 0, "relative_humidity_2m": 85, "visibility": 20000,
              "wind_speed_10m": 5, "temperature_2m": 6}
    hourly = {name: [value] * len(times) for name, value in values.items()}
    hourly["time"] = [int(t.timestamp()) for t in times]
    weather = replace(DEFAULT_WEATHER, retrieved_at_utc=reference, payload={"hourly": hourly},
                      valid_from=start, valid_until=times[-1], hour_count=len(times))
    with TestClient(create_app(weather_provider=lambda *a: weather, clock=lambda: reference)) as client:
        response = client.post("/v1/tonight", json={"selected_project_id": "M42", "availability": {
            "mode": "fixed_window", "start": "2026-10-25T21:00:00+01:00", "end": "2026-10-25T22:30:00+01:00"}})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "no_candidate"
        assert result["target_refusal"]["code"] == "target_below_minimum_altitude"
        assert not list((tmp_path / "decision_lineage").glob("*.json"))
    def unavailable(*args, **kwargs):
        raise AssertionError("No new weather or decision on restart/read")
    reloaded = TestClient(create_app(service_factory=unavailable, profile_provider=unavailable,
                                    weather_provider=unavailable))
    archived = reloaded.get("/v1/analysis-history/" + result["decision_id"])
    assert archived.status_code == 200, archived.text
    assert archived.json()["result"]["target_refusal"] == result["target_refusal"]
    assert archived.json()["request"]["availability"]["start"].startswith("2026-10-25T21:00")
    assert {p.name: p.read_bytes() for p in old.iterdir()} == before
    assert json.loads((tmp_path / "user_profile.json").read_text())["projects"]["M42"] == profile["projects"]["M42"]


def test_storage_limit_never_prunes_or_replaces_existing_records(tmp_path, monkeypatch):
    import astropilot.analysis_history as module
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    save(store, "first")
    before = (store.directory / "first.json").read_bytes()
    monkeypatch.setattr(module, "MAX_RECORDS", 1)
    with pytest.raises(AnalysisHistoryError, match="scan_limit"):
        save(store, "second")
    assert not (store.directory / "second.json").exists()
    assert (store.directory / "first.json").read_bytes() == before
    monkeypatch.setattr(module, "MAX_RECORDS", 512)
    monkeypatch.setattr(module, "MAX_TOTAL", len(before) + 1)
    with pytest.raises(AnalysisHistoryError, match="scan_limit"):
        save(store, "second")
    assert not (store.directory / "second.json").exists()
    assert (store.directory / "first.json").read_bytes() == before


def test_history_api_corruption_is_explicit_and_does_not_reset_files(tmp_path):
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    save(store)
    path = store.directory / (SHA_ID + ".json")
    path.write_bytes(b'{"invalid":true}')
    client = TestClient(create_app(analysis_store_factory=lambda: store))
    for endpoint in ["/v1/analysis-history", "/v1/analysis-history/" + SHA_ID]:
        response = client.get(endpoint)
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert str(tmp_path) not in response.text
    assert path.read_bytes() == b'{"invalid":true}'
    assert client.get("/v1/analysis-history", params={"before": "../outside"}).status_code == 422


def test_interrupted_publication_is_recovered_only_by_writer(tmp_path):
    import os
    store = FileAnalysisHistory(tmp_path / "analysis_history")
    save(store)
    path = store.directory / (SHA_ID + ".json")
    before = path.read_bytes()
    temporary = store.directory / ".analysis-deadbeef.tmp"
    os.link(path, temporary)  # Simulate a crash between link publication and temporary cleanup.
    with pytest.raises(AnalysisHistoryError):
        store.load(SHA_ID)
    assert temporary.exists(), "Read-only load must not clean up files"
    save(store)
    assert not temporary.exists()
    assert path.read_bytes() == before
    assert store.load(SHA_ID)["decision_id"] == SHA_ID


def test_fold_samples_remain_distinct_and_missing_geometry_does_not_blame_altitude(monkeypatch):
    from astropilot.engines.sky_engine import SkyEngine
    from astropilot.catalog import CATALOG
    sky = SkyEngine()
    hours = [{"time": datetime(2026, 10, 25, 2, tzinfo=ZONE, fold=fold)} for fold in (0, 1)]
    monkeypatch.setattr(sky, "target_altitude", lambda *args: -1)
    args = dict(sky=sky, hours=hours, target=CATALOG["M42"], catalog_key="M42",
                profile={"preferences": {}}, availability=None, lat=46.75, lon=6.55)
    assert missing_target_refusal(**args)["sample_count"] == 2
    monkeypatch.setattr(sky, "target_altitude", lambda *args: float("nan"))
    assert missing_target_refusal(**args)["code"] == "target_window_unavailable"
