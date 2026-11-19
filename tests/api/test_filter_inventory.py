"""Declared wheel inventory persists without credit, and gates discovery filters."""
import copy
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot.filter_inventory import declared_filter_ids
from astropilot.user_profile import load_user_profile


def test_inventory_persistence_revision_validation_and_configuration_preservation(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path/'profile'))
    client=TestClient(create_app())
    config={'site':{'name':'FICTIF','latitude':46.95,'longitude':7.45,'bortle':5},'equipment':{'preset_id':'samyang_183'},'projects':{}}
    created=client.put('/v1/configuration',json=config);assert created.status_code==200
    rev=created.json()['profile_revision']
    wheel={'wheel_name':'ZWO EFW TEST','slot_count':7,'slots':[
        {'position':1,'label':'Baader Ha Highspeed','filter_type':'Ha','filter_profile_id':'baader_ha_highspeed_6_5nm','bandwidth_nm':6.5},
        {'position':2,'label':'Filtre OIII fictif non catalogue','filter_type':'OIII','bandwidth_nm':3},
        {'position':3,'label':'Baader OIII Highspeed','filter_type':'OIII','filter_profile_id':'baader_oiii_highspeed_6_5nm','bandwidth_nm':6.5}]}
    payload={'expected_revision':rev,'equipment_id':'samyang_183','inventory':wheel}
    before=load_user_profile();assert declared_filter_ids(before,'samyang_183') is None
    response=client.put('/v1/filter-inventory',json=payload);assert response.status_code==200,response.text
    saved=load_user_profile();assert saved['projects']==before['projects'] and saved['sessions']==before['sessions']
    ids=declared_filter_ids(saved,'samyang_183');assert ids=={'baader_ha_highspeed_6_5nm','baader_oiii_highspeed_6_5nm'}
    assert declared_filter_ids(saved,'fra400') is None
    restarted=TestClient(create_app());assert restarted.get('/v1/filter-inventory').json()['inventories']['samyang_183']==wheel
    assert client.put('/v1/filter-inventory',json=payload).status_code==409
    payload['expected_revision']=saved['profile_revision']
    for invalid in [dict(wheel,slots=wheel['slots']+[wheel['slots'][0]]),dict(wheel,slot_count=2),dict(wheel,slots=[dict(wheel['slots'][0],filter_type='OIII')]),dict(wheel,slots=[dict(wheel['slots'][0],bandwidth_nm=3)]),dict(wheel,slots=[dict(wheel['slots'][0],position=0)])]:
        assert client.put('/v1/filter-inventory',json={**payload,'inventory':invalid}).status_code==422
    assert load_user_profile()==saved
    # A normal configuration save must not discard the separately declared wheel.
    response=client.put('/v1/configuration',json={**config,'expected_revision':saved['profile_revision']});assert response.status_code==200,response.text
    assert load_user_profile()['filter_inventories']==saved['filter_inventories']
    from astropilot.profile_backup import create_backup,inspect_backup,restore_empty
    import json
    raw,_=create_backup(tmp_path/'profile');files,_=inspect_backup(raw)
    restored=tmp_path/'restored';restore_empty(restored,files)
    assert json.loads((restored/'user_profile.json').read_text())['filter_inventories']==saved['filter_inventories']
    # Explicitly empty wheel must not fall back to fictitious built-in filters.
    payload['expected_revision']=response.json()['profile_revision'];payload['inventory']={**wheel,'slots':[]}
    assert client.put('/v1/filter-inventory',json=payload).status_code==200
    assert declared_filter_ids(load_user_profile(),'samyang_183')==set()


def test_discovery_rejects_filter_not_installed(tmp_path,monkeypatch):
    from test_target_discovery import profile,client_for,request,HA
    saved=profile();saved['filter_inventories']={'samyang_183':{'wheel_name':'FICTIF','slot_count':5,'slots':[]}}
    before=copy.deepcopy(saved)
    response=client_for(tmp_path,monkeypatch,saved=saved).post('/v1/target-suggestions',json=request())
    assert response.status_code==422 and response.json()['detail']['code']=='discovery_filter_not_installed'
    assert saved==before
