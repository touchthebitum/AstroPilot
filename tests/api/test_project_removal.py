"""Deletion preserves immutable historical credits and other projects."""
import copy
import json
import pytest
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot.user_profile import load_user_profile, save_user_profile, UserProfileError
from astropilot.profile_backup import create_backup, inspect_backup, restore_empty
from test_execution_session_api import setup, create_completed, credit

@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    api=TestClient(create_app())
    r=api.put('/v1/configuration',json={
        'site':{'name':'Buttes','latitude':46.886732,'longitude':6.548064,'bortle':4},
        'equipment':{'preset_id':'samyang_183'},
        'projects':{'IC1805':{'hours':0,'target_hours':20},'M42':{'hours':0,'target_hours':15}}})
    assert r.status_code==200,r.text
    return api

def remove(api,key='IC1805',**changes):
    return api.request('DELETE',f'/v1/projects/{key}',json={
        'expected_revision':load_user_profile()['profile_revision'],'confirmed':True,**changes})

def test_delete_reload_restore(api):
    before=copy.deepcopy(load_user_profile())
    r=remove(api);assert r.status_code==200,r.text
    after=load_user_profile()
    assert after['projects']=={'M42':before['projects']['M42']}
    assert after['archived_projects']=={'IC1805':before['projects']['IC1805']}
    fresh=TestClient(create_app())
    assert fresh.get('/v1/configuration').json()['archived_project_ids']==['IC1805']
    assert fresh.get('/v1/projects/IC1805/progress').status_code==200
    assert fresh.put('/v1/projects/IC1805/progress',json={'expected_revision':after['profile_revision']}).status_code==404
    r=fresh.post('/v1/projects/IC1805/restore',json={'expected_revision':after['profile_revision'],'confirmed':True})
    assert r.status_code==200,r.text
    assert load_user_profile()['projects']==before['projects']

@pytest.mark.parametrize('changes,status',[({'confirmed':False},422),({'confirmed':'true'},422),({'expected_revision':0},409),({'expected_revision':True},422)])
def test_refusal_without_write(api,tmp_path,changes,status):
    before=(tmp_path/'user_profile.json').read_bytes()
    assert remove(api,**changes).status_code==status
    assert (tmp_path/'user_profile.json').read_bytes()==before

def test_retry_and_unknown_project_without_write(api,tmp_path):
    revision=load_user_profile()['profile_revision']
    assert remove(api).status_code==200
    before=(tmp_path/'user_profile.json').read_bytes()
    assert remove(api,expected_revision=revision).status_code==409
    assert remove(api).status_code==404
    assert (tmp_path/'user_profile.json').read_bytes()==before

def test_configuration_preserves_archive_and_refuses_accidental_recreation(api):
    assert remove(api).status_code==200
    c=api.get('/v1/configuration').json()
    body={'expected_revision':c['profile_revision'],'site':{k:v for k,v in c['site'].items() if k!='timezone'},
          'equipment':{'preset_id':'samyang_183'},'projects':c['projects']}
    assert api.put('/v1/configuration',json=body).status_code==200
    archive=copy.deepcopy(load_user_profile()['archived_projects'])
    body['expected_revision']=load_user_profile()['profile_revision'];body['projects']['IC1805']={'hours':0,'target_hours':1}
    r=api.put('/v1/configuration',json=body)
    assert r.status_code==422,r.text
    assert r.json()['detail']['code']=='project_archived_restore_required'
    assert load_user_profile()['archived_projects']==archive

def test_backup_restore(api,tmp_path,monkeypatch):
    assert remove(api).status_code==200
    expected=copy.deepcopy(load_user_profile())
    raw,summary=create_backup(tmp_path)
    files,checked=inspect_backup(raw)
    assert all(checked[key] == value for key, value in summary.items())
    assert summary["projects"] == 2
    assert json.loads(files['user_profile.json'])==expected
    dest=tmp_path.parent/(tmp_path.name+'-restored')
    restore_empty(dest,files)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(dest))
    assert load_user_profile()==expected
    assert TestClient(create_app()).get('/v1/configuration').json()['archived_project_ids']==['IC1805']

def test_credited_history_and_replay(tmp_path,monkeypatch):
    # Entirely fictitious standard session fixture; no personal profile is read.
    fresh=setup(tmp_path,monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    assert credit(fresh(),'execution-1','evidence-1',confirm=True).status_code==200
    original=copy.deepcopy(load_user_profile())
    assert fresh().get('/v1/executions/execution-1/session').status_code==200
    lineage={p.name:p.read_bytes() for p in (tmp_path/'execution_lineage').iterdir() if p.is_file()}
    r=remove(fresh(),'Sh2-129');assert r.status_code==200,r.text
    assert load_user_profile()['intent_progress_credits']==original['intent_progress_credits']
    assert load_user_profile()['intent_progress_baselines']==original['intent_progress_baselines']
    r=fresh().get('/v1/executions/execution-1/session');assert r.status_code==200,r.text
    assert {p.name:p.read_bytes() for p in (tmp_path/'execution_lineage').iterdir() if p.is_file()}==lineage
    before=(tmp_path/'user_profile.json').read_bytes()
    assert credit(fresh(),'execution-1','evidence-1').json()['status']=='already_applied'
    assert (tmp_path/'user_profile.json').read_bytes()==before
    r=fresh().post('/v1/projects/Sh2-129/restore',json={'expected_revision':load_user_profile()['profile_revision'],'confirmed':True})
    assert r.status_code==200,r.text
    assert load_user_profile()['projects']==original['projects']

@pytest.mark.parametrize('archive',[[],{'IC1805':{}},{'Bad':{'hours':-1,'target_hours':1}}])
def test_archive_validation(api,archive):
    p=load_user_profile();p['archived_projects']=archive
    with pytest.raises(UserProfileError):save_user_profile(p,expected_revision=p['profile_revision'])
