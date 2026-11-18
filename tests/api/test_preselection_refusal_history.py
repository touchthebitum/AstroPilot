from copy import deepcopy
from dataclasses import replace
from fastapi.testclient import TestClient
from astropilot.app import create_app, TonightResponseModel
from astropilot.analysis_history import FileAnalysisHistory
from astro_score import build_durable_tonight_application_service
from test_target_discovery import REF, profile
from test_clean_machine_all_night_regression import _weather_snapshot
import pytest


def test_all_failed_windows_survive_api_and_read_only_history(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    saved = profile()
    saved['projects'] = {'Sh2-129': {'hours': 0, 'target_hours': 20,
        'imaging_field_id': 'sh2-129_ou4',
        'acquisition_intent_targets': [{'acquisition_intent_id':'ou4_oiii','target_hours':20}],
        'acquisition_intent_progress': [{'acquisition_intent_id':'ou4_oiii','acquired_duration_manual':0}]}}
    before = deepcopy(saved)
    weather = _weather_snapshot(reference_time=REF)
    payload = deepcopy(weather.payload)
    for key in ['cloud_cover','cloud_cover_low','cloud_cover_mid','cloud_cover_high']:
        payload['hourly'][key] = [100.0] * weather.hour_count
    weather = replace(weather, payload=payload)
    store = FileAnalysisHistory(tmp_path/'analysis_history')
    client = TestClient(create_app(profile_provider=lambda:saved, weather_provider=lambda *a:weather,
        clock=lambda:REF, service_factory=build_durable_tonight_application_service,
        analysis_store_factory=lambda:store))
    reply = client.post('/v1/tonight',json={'selected_project_id':'Sh2-129','availability':{
        'mode':'fixed_window','start_local':'2026-08-29T22:00','end_local':'2026-08-30T02:00',
        'preparation_minutes':20,'flats_minutes':5}})
    assert reply.status_code == 200,reply.text
    result = reply.json()
    assert result['status'] == 'no_mission'
    refusals = result['preselection_window_refusals']
    assert len(refusals) > 1
    assert all(r['productivity_breakdown']['productive_slice_count']==0 for r in refusals)
    assert saved == before
    assert client.get('/v1/accepted-missions').json() == []
    assert client.get('/v1/execution-sessions').json() == []
    record = store.load(result['decision_id'])
    assert record['result']['preselection_window_refusals'] == refusals
    def forbidden(*a,**kw):raise AssertionError('History must be read-only')
    reopened = TestClient(create_app(profile_provider=forbidden,weather_provider=forbidden,
        service_factory=forbidden,analysis_store_factory=lambda:store))
    files = {str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    response = reopened.get('/v1/analysis-history/'+result['decision_id'])
    assert response.status_code == 200
    assert response.json()['result']['preselection_window_refusals'] == refusals
    assert files == {str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    # Old analyses without this optional evidence remain valid and unexpanded.
    old = {k:v for k,v in result.items() if k!='preselection_window_refusals'}
    assert 'preselection_window_refusals' not in TonightResponseModel.model_validate(old).model_dump(mode='json')
    with pytest.raises(ValueError,match='preselection_refusals_require_no_mission'):
        TonightResponseModel.model_validate({**result,'status':'no_recommendation'})
