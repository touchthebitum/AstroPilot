"""Real calculation and archive with synthetic weather and isolated M42/Ou4 data."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
import astro_score
from astropilot.app import create_app
from astropilot.analysis_history import FileAnalysisHistory
from decision.weather.weather_ingress import REQUIRED_HOURLY_UNITS,validate_weather_payload

ZONE=ZoneInfo('Europe/Zurich')


def weather_at(reference):
    start=datetime(2026,11,1,tzinfo=ZONE)
    n=24*7
    return validate_weather_payload({
        'latitude':46.886732,'longitude':6.548064,'elevation':790.,
        'timezone':'Europe/Zurich','utc_offset_seconds':3600,
        'hourly_units':{'time':'unixtime',**REQUIRED_HOURLY_UNITS},
        'hourly':{'time':[int((start+timedelta(hours=i)).timestamp()) for i in range(n)],
            'cloud_cover':[0.]*n,'cloud_cover_low':[0.]*n,'cloud_cover_mid':[0.]*n,'cloud_cover_high':[0.]*n,
            'precipitation':[0.]*n,'relative_humidity_2m':[45.]*n,'visibility':[24000.]*n,
            'wind_speed_10m':[2.]*n,'temperature_2m':[12.]*n}},
        requested_latitude=46.886732,requested_longitude=6.548064,
        requested_timezone='Europe/Zurich',retrieved_at_utc=reference-timedelta(minutes=2))


@pytest.mark.parametrize('local,key,field,intent',[
    ('2026-11-02T21:46:07+01:00','Sh2-129','sh2-129_ou4','ou4_oiii'),
    ('2026-11-03T01:30:00+01:00','M42','m42','m42_ha'),
])
def test_real_saved_intent_future_bounds_acceptance_and_archive_are_durable(tmp_path,monkeypatch,local,key,field,intent):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    reference=datetime.fromisoformat(local)
    weather=weather_at(reference)
    history=FileAnalysisHistory(tmp_path/'analysis_history')
    def factory():
        service=astro_score.build_durable_tonight_application_service()
        service.clock=lambda:reference
        return service
    client=TestClient(create_app(service_factory=factory,weather_provider=lambda *a:weather,
        clock=lambda:reference,analysis_store_factory=lambda:history))
    response=client.put('/v1/configuration',json={
        'site':{'name':'Synthetic Buttes','latitude':46.886732,'longitude':6.548064,'bortle':4},
        'equipment':{'preset_id':'samyang_183'},
        'projects':{key:{'hours':0,'target_hours':20,'imaging_field_id':field,
            'acquisition_intent_targets':[{'acquisition_intent_id':intent,'target_hours':20}],
            'acquisition_intent_progress':[{'acquisition_intent_id':intent,'acquired_duration_manual':0}]}}})
    assert response.status_code==200,response.text
    from test_saved_observation_catalogue import seed
    from tests.architecture.test_outcome_evaluation_persistence_contract import evaluation
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    seed(tmp_path)
    comparisons=FileOutcomeEvaluationStore(tmp_path/'outcome_evaluations')
    for i in range(3):
        comparisons.save(evaluation=evaluation(execution=False,comparison_id=str(i+1)*64))
    preserved={p.relative_to(tmp_path):p.read_bytes() for folder in ('field_observations','outcome_evaluations')
               for p in (tmp_path/folder).glob('*.json')}
    protected=tmp_path/'user_profile.json'
    profile_before=protected.read_bytes()
    request={'availability':{'mode':'all_night'},'selected_project_id':key}
    result=client.post('/v1/tonight',json=request)
    assert result.status_code==200,result.text
    decision=result.json()
    assert decision['status']=='available',decision
    start=datetime.fromisoformat(decision['window_start'])
    end=datetime.fromisoformat(decision['window_end'])
    assert start.astimezone(timezone.utc)>=reference.astimezone(timezone.utc)
    assert end.astimezone(timezone.utc)>start.astimezone(timezone.utc)
    from astropilot.engines.sky_engine import SkyEngine
    _, dawn=SkyEngine.astronomical_night_window(datetime(2026,11,2).date(),46.886732,6.548064,ZONE)
    assert end.astimezone(timezone.utc)<=dawn.astimezone(timezone.utc)
    assert end.astimezone(timezone.utc)-start.astimezone(timezone.utc)>=timedelta(hours=1)
    assert decision['night_date']=='2026-11-02'
    selection=client.post('/v1/decision-selections',json={
        'acceptance_request_id':'remaining-night-'+key,'decision_id':decision['decision_id'],
        'source':'primary_recommendation','selected_catalog_key':key,
        'acquisition_intent_id':intent,'selected_at':reference.isoformat()})
    assert selection.status_code==200,selection.text
    mission=selection.json()['mission']
    assert datetime.fromisoformat(mission['window_start']).astimezone(timezone.utc)>=reference.astimezone(timezone.utc)
    assert datetime.fromisoformat(mission['window_end']).astimezone(timezone.utc)<=dawn.astimezone(timezone.utc)
    assert protected.read_bytes()==profile_before
    assert len(list((tmp_path/'field_observations').glob('*.json')))==3
    assert all((tmp_path/p).read_bytes()==raw for p,raw in preserved.items())
    assert not list((tmp_path/'execution_lineage').glob('*.json'))
    archived=history.load(decision['decision_id'])
    assert archived['request']['availability']=={'mode':'all_night'}
    assert archived['result']['window_start']==decision['window_start']
    snapshot={p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*.json')}
    def forbidden(*a,**kw):raise AssertionError('A reread must not calculate or load the profile')
    restarted=TestClient(create_app(service_factory=forbidden,weather_provider=forbidden,
        profile_provider=forbidden,analysis_store_factory=lambda:FileAnalysisHistory(history.directory)))
    reread=restarted.get('/v1/analysis-history/'+decision['decision_id'])
    assert reread.status_code==200,reread.text
    assert reread.json()['result']==archived['result']
    assert {p.relative_to(tmp_path).as_posix():p.read_bytes() for p in tmp_path.rglob('*.json')}==snapshot


def test_clear_past_cannot_authorize_cloudy_remaining_night(tmp_path,monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    reference=datetime(2026,11,2,21,46,7,tzinfo=ZONE)
    weather=weather_at(reference)
    # Preserve a good past evening, but make every future weather hour covered.
    payload=deepcopy(weather.payload)
    for i,stamp in enumerate(payload['hourly']['time']):
        if stamp>=datetime(2026,11,2,21,tzinfo=ZONE).timestamp():
            payload['hourly']['cloud_cover'][i]=100.
    weather=validate_weather_payload(payload,requested_latitude=46.886732,
        requested_longitude=6.548064,requested_timezone='Europe/Zurich',retrieved_at_utc=reference)
    def factory():
        service=astro_score.build_durable_tonight_application_service()
        service.clock=lambda:reference
        return service
    client=TestClient(create_app(service_factory=factory,weather_provider=lambda *a:weather,clock=lambda:reference))
    response=client.put('/v1/configuration',json={
        'site':{'name':'Synthetic Buttes','latitude':46.886732,'longitude':6.548064,'bortle':4},
        'equipment':{'preset_id':'samyang_183'},'projects':{'Sh2-129':{
            'hours':0,'target_hours':20,'imaging_field_id':'sh2-129_ou4',
            'acquisition_intent_targets':[{'acquisition_intent_id':'ou4_oiii','target_hours':20}],
            'acquisition_intent_progress':[{'acquisition_intent_id':'ou4_oiii','acquired_duration_manual':0}]}}})
    assert response.status_code==200,response.text
    before=(tmp_path/'user_profile.json').read_bytes()
    response=client.post('/v1/tonight',json={'availability':{'mode':'all_night'},'selected_project_id':'Sh2-129'})
    assert response.status_code==200,response.text
    assert response.json()['status']!='available',response.json()
    assert response.json()['recommended_hours']==0
    assert (tmp_path/'user_profile.json').read_bytes()==before


def test_discovery_suggestions_also_use_remaining_night_without_writes(tmp_path,monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    reference=datetime(2026,11,2,21,46,7,tzinfo=ZONE)
    profile={'location':{'name':'Synthetic Buttes','latitude':46.886732,'longitude':6.548064},
        'preferences':{'bortle':4},'active_equipment':'samyang_183','available_equipment':['samyang_183'],
        'projects':{},'sessions':[]}
    original=deepcopy(profile)
    client=TestClient(create_app(profile_provider=lambda:profile,weather_provider=lambda *a:weather_at(reference),clock=lambda:reference))
    response=client.post('/v1/target-suggestions',json={'availability':{'mode':'all_night'},
        'confirmed_filter_profile_ids':['baader_ha_highspeed_6_5nm']})
    assert response.status_code==200,response.text
    assert response.json()['status']=='suggestions',response.json()
    for suggestion in response.json()['suggestions']:
        assert datetime.fromisoformat(suggestion['window_start']).astimezone(timezone.utc)>=reference.astimezone(timezone.utc)
    assert profile==original
    assert not list(tmp_path.rglob('*.json'))
