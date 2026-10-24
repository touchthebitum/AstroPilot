"""A saved single-filter project is not a promise of a productive night."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
import astro_score
from astropilot.app import create_app
from decision.weather.weather_ingress import REQUIRED_HOURLY_UNITS, validate_weather_payload


@pytest.mark.parametrize('cloud_cover,available', [(10, True), (65, False), (100, False)])
def test_saved_ha_project_distinguishes_unusable_window_from_missing_configuration(
    tmp_path, monkeypatch, cloud_cover, available,
):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    reference = datetime(2026, 10, 18, 11, tzinfo=timezone.utc)
    start = datetime(2026, 10, 18, tzinfo=ZoneInfo('Europe/Zurich'))
    n = 24 * 7
    weather = validate_weather_payload({
        'latitude':46.888, 'longitude':6.55, 'elevation':837.,
        'timezone':'Europe/Zurich', 'utc_offset_seconds':7200,
        'hourly_units':{'time':'unixtime', **REQUIRED_HOURLY_UNITS},
        'hourly':{
            'time':[int((start + timedelta(hours=i)).timestamp()) for i in range(n)],
            'cloud_cover':[float(cloud_cover)]*n,
            'cloud_cover_low':[5.]*n, 'cloud_cover_mid':[3.]*n, 'cloud_cover_high':[2.]*n,
            'precipitation':[0.]*n, 'relative_humidity_2m':[60.]*n,
            'visibility':[24000.]*n, 'wind_speed_10m':[5.]*n, 'temperature_2m':[12.]*n,
        },
    }, requested_latitude=46.888, requested_longitude=6.55,
        requested_timezone='Europe/Zurich', retrieved_at_utc=reference-timedelta(minutes=5))
    assembly_calls = []
    original = astro_score.tonight_mission_service.create_with_actionability_diagnostic

    def assemble(**kwargs):
        assembly_calls.append(kwargs['recommended_key'])
        assert available, 'A candidate without any eligible intent must not reach mission assembly'
        return original(**kwargs)

    monkeypatch.setattr(astro_score.tonight_mission_service,
        'create_with_actionability_diagnostic', assemble)
    client = TestClient(create_app(
        service_factory=astro_score.build_durable_tonight_application_service,
        weather_provider=lambda *_: weather, clock=lambda: reference,
    ))
    project = {
        'hours':0, 'target_hours':10, 'imaging_field_id':'sh2-129_ou4',
        'acquisition_intent_targets':[{'acquisition_intent_id':'sh2-129_ha','target_hours':10}],
        'acquisition_intent_progress':[{'acquisition_intent_id':'sh2-129_ha','acquired_duration_manual':0}],
    }
    saved = client.put('/v1/configuration', json={
        'site':{'name':'Fixture', 'latitude':46.888, 'longitude':6.55, 'bortle':4},
        'equipment':{'preset_id':'samyang_183'}, 'projects':{'Sh2-129':project},
    })
    assert saved.status_code == 200, saved.text
    path = tmp_path/'user_profile.json'
    before = path.read_bytes()
    response = client.post('/v1/tonight', json={
        'availability':{'mode':'fixed_window','start_local':'2026-10-18T20:00','end_local':'2026-10-18T23:00'},
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['catalog_key'] == 'Sh2-129'
    assert payload['provenance'] == 'project'
    if available:
        assert payload['status'] == 'available'
        assert payload['selected_acquisition_intent_id'] == 'sh2-129_ha'
        assert payload['creation_refusal'] is None
        assert assembly_calls == ['Sh2-129']
    else:
        assert payload['status'] == 'no_mission'
        assert payload['creation_refusal'] == 'no_eligible_acquisition_intent'
        assert payload['selected_acquisition_intent_id'] is None
        assert payload['recommended_hours'] == 0
        assessments = {item['acquisition_intent_id']:item for item in payload['acquisition_intent_assessments']}
        assert assessments['sh2-129_ha']['reason_codes'] == ['insufficient_actionable_productive_window']
        assert assessments['ou4_oiii']['reason_codes'] == ['intent_not_targeted_by_project']
        assert assembly_calls == []
        summary = payload['refusal_weather']
        assert summary['cloud_cover_min'] == cloud_cover
        assert summary['cloud_cover_max'] == cloud_cover
        assert summary['window_start'] == '2026-10-18T21:00:00+02:00'
        assert summary['window_end'] == '2026-10-18T23:00:00+02:00'
        assert summary['retrieved_at_utc'] == '2026-10-18T10:55:00Z'

    assert path.read_bytes() == before
