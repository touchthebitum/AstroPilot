"""Geometric guidance is read-only and cannot authorize a mission."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from astropilot.altitude_guidance import altitude_guidance, _sampled_intervals, GuidanceError
from astropilot.app import create_app, SessionAvailabilityRequest
from astropilot.engines.sky_engine import SkyEngine
from astropilot.user_profile import save_user_profile
from decision.location.location_time import LocationTimeResolver
from test_tonight_api import valid_profile

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def profile():
    return {**valid_profile(), "projects": {"M42": {"hours": 0, "target_hours": 15,
        "imaging_field_id": "m42", "acquisition_intent_targets": [
            {"acquisition_intent_id": "m42_ha", "target_hours": 15}],
        "acquisition_intent_progress": [{"acquisition_intent_id": "m42_ha", "acquired_duration_manual": 0}]}}}


def test_M42_real_geometry_and_production_threshold_without_weather():
    p = profile(); original = deepcopy(p)
    result = altitude_guidance(profile=p, project_id="M42", reference_time=NOW)
    assert result.status == "available" and result.astronomical_only
    assert result.night_date == date(2026, 10, 27)
    assert result.minimum_altitude_deg == 30 and result.required_continuous_minutes == 60
    assert result.timezone == "Europe/Zurich" and 2 < len(result.points) < 300
    assert result.intervals
    zone = LocationTimeResolver.resolve(46.7508, 6.5495).zone
    sky = SkyEngine()
    for item in result.intervals:
        assert item.start >= NOW and item.start < item.end <= result.night_end
        assert item.duration_minutes == (item.end-item.start).total_seconds()/60
        assert item.start.astimezone(zone).date() == date(2026, 10, 28)
        # Both bounds and all minutes inside satisfy the same production geometry.
        times = [item.start + timedelta(minutes=i) for i in range(item.duration_minutes + 1)]
        assert all(a >= 30 for a in sky.target_altitudes(83.8221, -5.3911, times, 46.7508, 6.5495))
        request = SessionAvailabilityRequest(mode="fixed_window", start=item.start, end=item.end)
        assert request.to_domain().start == item.start
    assert p == original


def test_sampled_intervals_do_not_bridge_low_slice_or_round_short_window_up():
    times = [NOW+timedelta(minutes=i) for i in range(130)]
    altitudes = [40]*60 + [29] + [40]*69
    items = _sampled_intervals(times, altitudes, 30, NOW-timedelta(hours=1))
    assert [(i.duration_minutes,i.can_analyze) for i in items] == [(59,False),(68,True)]
    assert items[0].end < items[1].start
    current = _sampled_intervals(times, altitudes, 30, NOW+timedelta(minutes=70,seconds=30))
    assert current[0].start == NOW+timedelta(minutes=71)
    assert current[0].duration_minutes == 58 and not current[0].can_analyze
    assert not _sampled_intervals(times, altitudes,30,NOW+timedelta(days=1))


def test_configured_threshold_is_used_without_modifying_it():
    p=profile();p["preferences"]["min_altitude_deg"]=70
    original=deepcopy(p)
    result=altitude_guidance(profile=p,project_id="M42",reference_time=NOW)
    assert result.minimum_altitude_deg==70 and result.status=="no_altitude_window"
    assert not result.intervals and max(p.altitude_deg for p in result.points)<70
    assert p==original


@pytest.mark.parametrize("night", [date(2026,3,28), date(2026,10,24)])
def test_dst_nights_use_absolute_instants_and_site_offsets(night):
    now=datetime.combine(night,datetime.min.time(),timezone.utc)+timedelta(hours=12)
    result=altitude_guidance(profile=profile(),project_id="M42",reference_time=now,night_date=night)
    times=[p.time for p in result.points]
    assert times==sorted(set(times)) and result.night_start<result.night_end
    zone=LocationTimeResolver.resolve(46.7508,6.5495).zone
    assert result.night_start.astimezone(zone).utcoffset()!=result.night_end.astimezone(zone).utcoffset()
    for interval in result.intervals:
        assert interval.duration_minutes==(interval.end-interval.start).total_seconds()/60


def test_default_before_dawn_stays_in_current_night_and_filters_elapsed_time():
    now=datetime(2026,10,28,3,tzinfo=timezone.utc)
    result=altitude_guidance(profile=profile(),project_id="M42",reference_time=now)
    assert result.night_date==date(2026,10,27)
    assert all(i.start>=now for i in result.intervals)


def test_missing_astronomical_night_or_invalid_samples_fail_closed():
    sky=Mock()
    sky.astronomical_night_window.side_effect=ValueError("no twilight")
    result=altitude_guidance(profile=profile(),project_id="M42",reference_time=NOW,sky=sky)
    assert result.status=="astronomical_night_unavailable" and not result.intervals and not result.points
    sky.target_altitudes.assert_not_called()
    sky.astronomical_night_window.side_effect=None
    sky.astronomical_night_window.return_value=(NOW,NOW+timedelta(hours=2))
    sky.target_altitudes.return_value=[float("nan")]*121
    with pytest.raises(GuidanceError,match="guidance_calculation_unavailable"):
        altitude_guidance(profile=profile(),project_id="M42",reference_time=NOW,sky=sky)


@pytest.mark.parametrize("path", [
    "/v1/projects/not-saved/altitude-guidance",
    "/v1/projects/M42/altitude-guidance?night_date=2030-01-01",
    "/v1/projects/M42/altitude-guidance?night_date=2026-02-30",
])
def test_bad_requests_do_not_call_forecast(path):
    weather=Mock(side_effect=AssertionError("weather must not be read"))
    service=SimpleNamespace(evaluate=Mock(side_effect=AssertionError("no decision")))
    with TestClient(create_app(service_factory=lambda:service,profile_provider=profile,
                              weather_provider=weather,clock=lambda:NOW)) as client:
        assert client.get(path).status_code==422
    weather.assert_not_called();service.evaluate.assert_not_called()


def test_api_restart_reads_leave_saved_Ha_project_and_three_reports_intact(tmp_path,monkeypatch):
    from astropilot.user_profile import load_user_profile
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    from tests.architecture.test_outcome_evaluation_persistence_contract import evaluation
    from test_saved_observation_catalogue import seed
    monkeypatch.setenv("ASTROPILOT_DATA_DIR",str(tmp_path))
    save_user_profile(profile());seed(tmp_path)
    store=FileOutcomeEvaluationStore(tmp_path/"outcome_evaluations")
    for i in range(3):store.save(evaluation=evaluation(execution=False,comparison_id=str(i+1)*64))
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    weather=Mock(side_effect=AssertionError("no weather")); service=SimpleNamespace(evaluate=Mock(side_effect=AssertionError("no decision")))
    responses=[]
    for _ in range(2):
        with TestClient(create_app(service_factory=lambda:service,profile_provider=load_user_profile,
                                  weather_provider=weather,clock=lambda:NOW)) as client:
            response=client.get('/v1/projects/M42/altitude-guidance')
            assert response.status_code==200,response.text
            assert response.headers['Cache-Control']=='no-store'
            responses.append(response.json())
        assert {p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before
    assert responses[0]==responses[1]
    weather.assert_not_called();service.evaluate.assert_not_called()
