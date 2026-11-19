"""Existing portfolio comparison preserves counters and requires explicit goals."""
from copy import deepcopy
import pytest
from test_selected_project_continuity import portfolio


def compare(client):
    return client.post('/v1/tonight', json={'compare_projects': True,
        'availability': {'mode':'all_night', 'preparation_minutes':20, 'flats_minutes':5}})


def test_compare_uses_only_existing_projects_and_preserves_progress(portfolio):
    client, _ = portfolio
    before=deepcopy(client.get('/v1/configuration').json())
    response=compare(client)
    assert response.status_code==200, response.text
    data=response.json()
    assert data['catalog_key'] in before['projects']
    assert all(row['catalog_key'] in before['projects'] for row in data['alternatives'])
    assert {row['project_id'] for row in data['project_comparison']}==set(before['projects'])
    for p in data['project_comparison']:
        ha=next(r for r in p['filters'] if r['filter_type']=='Ha')
        assert ha['target_hours']==3 and ha['acquired_hours']==0 and ha['remaining_hours']==3
        assert ha['status']=='to_complete'
    assert client.get('/v1/configuration').json()==before
    assert client.get('/v1/accepted-mission/current').json() is None
    assert client.get('/v1/execution-sessions').json()==[]


def test_completed_and_unknown_projects_are_not_selected(portfolio):
    client, _=portfolio
    config=client.get('/v1/configuration').json()
    saved=deepcopy(config['projects'])
    # M42 completed; NorthAmerica's progress is explicitly unknown.
    saved['M42']['acquisition_intent_progress'][0]['acquired_duration_manual']=3*3600
    saved['NorthAmerica']['acquisition_intent_progress']=[]
    response=client.put('/v1/configuration',json={
        'expected_revision':config['profile_revision'],
        'site':{'name':'Synthetic','latitude':46.888,'longitude':6.55,'bortle':4},'equipment':{'preset_id':'samyang_183'},'projects':saved})
    assert response.status_code==200,response.text
    result=compare(client)
    assert result.status_code==200,result.text
    data=result.json()
    assert data['status']!='available' and data.get('catalog_key') is None
    by_project={p['project_id']:p['filters'] for p in data['project_comparison']}
    assert next(r for r in by_project['M42'] if r['filter_type']=='Ha')['status']=='completed'
    assert next(r for r in by_project['NorthAmerica'] if r['filter_type']=='Ha')['remaining_hours'] is None
    assert client.get('/v1/accepted-mission/current').json() is None


def test_weather_refusal_preserves_comparison_and_counters(portfolio):
    from test_orion_discovery import winter_weather
    client,weather=portfolio
    before=deepcopy(client.get('/v1/configuration').json())
    weather[0]=winter_weather(clouds=100)
    result=compare(client)
    assert result.status_code==200,result.text
    assert result.json()['status']!='available'
    assert result.json()['project_comparison']
    assert client.get('/v1/configuration').json()==before
    assert client.get('/v1/accepted-mission/current').json() is None


def test_comparison_and_explicit_project_are_mutually_exclusive(portfolio):
    client,_=portfolio
    response=client.post('/v1/tonight',json={'compare_projects':True,'selected_project_id':'M42'})
    assert response.status_code==422


def test_rosette_filter_counters_are_separate_and_completed_filter_excluded(portfolio):
    client,_=portfolio
    cfg=client.get('/v1/configuration').json()
    rosette={'hours':0,'target_hours':6,'imaging_field_id':'rosette',
        'acquisition_intent_targets':[{'acquisition_intent_id':'rosette_'+f,'target_hours':3}
            for f in ['ha','oiii','sii']],
        'acquisition_intent_progress':[{'acquisition_intent_id':'rosette_'+f,'acquired_duration_manual':seconds}
            for f,seconds in [('ha',10800),('oiii',2400),('sii',1500)]]}
    r=client.put('/v1/configuration',json={'expected_revision':cfg['profile_revision'],
        'site':{'name':'Synthetic','latitude':46.888,'longitude':6.55,'bortle':4},
        'equipment':{'preset_id':'samyang_183'},'projects':{'Rosette':rosette}})
    assert r.status_code==200,r.text
    before=deepcopy(client.get('/v1/projects/Rosette/progress').json())
    r=compare(client);assert r.status_code==200,r.text
    data=r.json();rows={r['filter_type']:r for r in data['project_comparison'][0]['filters']}
    assert rows['Ha']['remaining_hours']==0 and rows['Ha']['status']=='completed'
    assert rows['OIII']['acquired_hours']==pytest.approx(40/60)
    assert rows['SII']['acquired_hours']==pytest.approx(25/60)
    assert rows['OIII']['remaining_hours']==pytest.approx(3-40/60)
    assert rows['SII']['remaining_hours']==pytest.approx(3-25/60)
    assert data.get('selected_acquisition_intent_id')!='rosette_ha'
    assert 'rosette_ha' not in data.get('viable_acquisition_intent_ids',[])
    assert client.get('/v1/projects/Rosette/progress').json()==before
    assert client.get('/v1/accepted-mission/current').json() is None
    assert client.get('/v1/execution-sessions').json()==[]


def test_removed_projects_are_excluded_and_empty_portfolio_explained(portfolio):
    client,_=portfolio
    cfg=client.get('/v1/configuration').json()
    r=client.request('DELETE','/v1/projects/NorthAmerica',json={'expected_revision':cfg['profile_revision'],'confirmed':True})
    assert r.status_code==200,r.text
    data=compare(client).json()
    assert [p['project_id'] for p in data['project_comparison']]==['M42']
    cfg=client.get('/v1/configuration').json()
    r=client.request('DELETE','/v1/projects/M42',json={'expected_revision':cfg['profile_revision'],'confirmed':True})
    assert r.status_code==200,r.text
    r=compare(client)
    assert r.status_code==422 and r.json()['detail']['code']=='project_comparison_empty'
    assert client.get('/v1/accepted-mission/current').json() is None


def test_comparison_refuses_broken_credit_lineage(tmp_path,monkeypatch):
    from test_execution_session_api import setup,create_completed,credit
    fresh=setup(tmp_path,monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    assert credit(fresh(),'execution-1','evidence-1',confirm=True).status_code==200
    canonical=fresh().get('/v1/projects/Sh2-129/progress').json()
    ha=next(r for r in canonical['acquisition_intent_remaining_progress']
        if r['acquisition_intent_id']=='sh2-129_ha')
    assert ha['acquired_hours']==1.5
    path=tmp_path/'user_profile.json';before=path.read_bytes()
    (tmp_path/'execution_lineage/execution-1.json').unlink()
    r=compare(fresh())
    assert r.status_code==503 and r.json()['detail']['code']=='project_credit_inconsistent'
    assert path.read_bytes()==before
