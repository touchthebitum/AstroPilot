"""Old accepted plans remain readable without inventing executions or credits."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
from astropilot.app import create_app
from test_target_discovery import november_weather


def test_all_saved_plans_survive_restart_expiry_and_profile_revision(tmp_path,monkeypatch):
    from astro_score import build_durable_tonight_application_service
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    ref=datetime(2026,11,10,18,tzinfo=timezone.utc)
    clock=[ref]
    def client():
        def service():
            result=build_durable_tonight_application_service()
            result.clock=lambda:clock[0]
            return result
        return TestClient(create_app(service_factory=service,clock=lambda:clock[0],
            weather_provider=lambda *a:november_weather(ref)))
    api=client()
    config={'site':{'name':'FICTIF','latitude':46.888,'longitude':6.55,'bortle':4},
        'equipment':{'preset_id':'samyang_183'},'projects':{'Rosette':{'hours':0,'target_hours':4,
        'imaging_field_id':'rosette','acquisition_intent_targets':[
            {'acquisition_intent_id':'rosette_oiii','target_hours':3},
            {'acquisition_intent_id':'rosette_sii','target_hours':4}],
        'acquisition_intent_progress':[{'acquisition_intent_id':'rosette_oiii','acquired_duration_manual':2400},
            {'acquisition_intent_id':'rosette_sii','acquired_duration_manual':900}]}}}
    assert api.put('/v1/configuration',json=config).status_code==200
    assert api.get('/v1/accepted-missions').json()==[]
    progress=api.get('/v1/projects/Rosette/progress').json()
    plans=[]
    for _ in range(2):
        decision=api.post('/v1/tonight',json={'selected_project_id':'Rosette','availability':{
            'mode':'fixed_window','start':'2026-11-14T03:00:00+01:00','end':'2026-11-14T05:00:00+01:00',
            'preparation_minutes':20,'flats_minutes':5}})
        assert decision.status_code==200,decision.text
        response=api.post('/v1/decision-selections',json={'acceptance_request_id':str(uuid.uuid4()),
            'decision_id':decision.json()['decision_id'],'source':'primary_recommendation',
            'selected_catalog_key':'Rosette','acquisition_intent_id':'rosette_sii','selected_at':clock[0].isoformat()})
        assert response.status_code==200,response.text
        plans.append(response.json());clock[0]+=timedelta(seconds=1)
    assert plans[0]['mission_id']!=plans[1]['mission_id']
    assert api.get('/v1/accepted-mission/current').json()==plans[1]
    def hashes():return {str(p.relative_to(tmp_path)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in tmp_path.rglob('*') if p.is_file()}
    def plans_only(items):return [{k:v for k,v in item.items() if k!="selected_at"} for item in items]
    before=hashes()
    restarted=client();response=restarted.get('/v1/accepted-missions')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert plans_only(response.json())==list(reversed(plans))
    assert [datetime.fromisoformat(item["selected_at"]) for item in response.json()]==[ref+timedelta(seconds=1),ref]
    assert hashes()==before
    for item in response.json():
        assert item['mission']['acquisition_intent_id']=='rosette_sii'
        assert item['mission']['tasks'][0]['start']=='T-20 min'
        assert item['mission']['tasks'][-1]['end']=='Fin +5 min'
    clock[0]=datetime(2026,11,15,tzinfo=timezone.utc)
    assert restarted.get('/v1/accepted-mission/current').json() is None
    assert plans_only(restarted.get('/v1/accepted-missions').json())==list(reversed(plans))
    configuration=restarted.get('/v1/configuration').json()
    config['expected_revision']=configuration['profile_revision'];config['site']['name']='AUTRE NOM FICTIF'
    assert restarted.put('/v1/configuration',json=config).status_code==200
    assert plans_only(restarted.get('/v1/accepted-missions').json())==list(reversed(plans))
    revised_progress=restarted.get('/v1/projects/Rosette/progress').json()
    assert {k:v for k,v in revised_progress.items() if k!='profile_revision'}=={
        k:v for k,v in progress.items() if k!='profile_revision'}
    assert restarted.get('/v1/execution-sessions').json()==[]
    # A damaged history is an explicit failure, never a false complete empty list.
    path=next((tmp_path/'decision_lineage').glob('*.json'));path.write_text('{broken')
    failed=restarted.get('/v1/accepted-missions')
    assert failed.status_code==503
    assert failed.json()['detail']['code']=='acceptance_lineage_unavailable'
