"""A moved managed kit cannot look empty, accept writes, or lose its identity."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot.launcher_context import ENVIRONMENT_KEY, LaunchSession
from astropilot.profile_transfer_app import create_transfer_app


def managed(tmp_path,monkeypatch):
    kit=tmp_path/'Kit été';kit.mkdir();profile=kit/'DONNEES-PERSONNELLES/profil'
    info=kit.stat();value={'session_id':'a'*64,'kit_directory':str(kit),'data_directory':str(profile),'kit_device':info.st_dev,'kit_inode':info.st_ino}
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(profile));monkeypatch.setenv(ENVIRONMENT_KEY,json.dumps(value))
    return kit,profile,value

@pytest.mark.parametrize('assistant',[False,True])
def test_move_blocks_reads_and_writes_before_touching_old_location(tmp_path,monkeypatch,assistant):
    kit,profile,value=managed(tmp_path,monkeypatch)
    app=create_transfer_app(directory=profile,origin='http://testserver') if assistant else create_app()
    api=TestClient(app)
    initial=api.get('/v1/runtime-identity');assert initial.status_code==200
    context=api.get('/v1/launcher-context')
    assert context.json()['location_status']=='available'
    if not assistant:assert context.headers.get('X-NightMerit-Time-Authority')
    moved=tmp_path/'Déplacé';kit.rename(moved)
    # Package metadata is deliberately made unavailable after startup.
    import astropilot.app as module
    monkeypatch.setattr(module,'canonical_version',lambda:(_ for _ in ()).throw(RuntimeError('bundle moved')))
    identity=api.get('/v1/runtime-identity');assert identity.status_code==200
    assert identity.json()==initial.json()
    context=api.get('/v1/launcher-context');assert context.status_code==200
    assert context.json()['session_id']==value['session_id']
    assert context.json()['location_status']=='moved_or_unavailable'
    if assistant:
        read=api.get('/transfer/status')
    else:read=api.get('/v1/configuration')
    assert read.status_code==409,read.text
    assert read.json()['detail']['code']=='kit_moved_or_unavailable'
    assert api.get('/').status_code==409
    assert not kit.exists() and not (moved/'DONNEES-PERSONNELLES').exists()


def test_moved_application_diagnostic_survives_but_configuration_write_is_blocked(tmp_path,monkeypatch):
    kit,profile,_=managed(tmp_path,monkeypatch);api=TestClient(create_app())
    kit.rename(tmp_path/'Moved')
    response=api.put('/v1/configuration',json={})
    assert response.status_code==409 and response.json()['detail']['code']=='kit_moved_or_unavailable'
    assert api.get('/v1/data-context').status_code==200
    assert not kit.exists()


def test_assistant_cannot_restore_into_abandoned_old_path(tmp_path,monkeypatch):
    kit,profile,_=managed(tmp_path,monkeypatch);api=TestClient(create_transfer_app(directory=profile,origin='http://testserver'))
    import re
    token=re.search(r'const token="([^"]+)"',api.get('/').text).group(1)
    kit.rename(tmp_path/'Moved')
    response=api.post('/transfer/restore',json={'confirm':True,'confirmation':'anything'},headers={'X-NightMerit-Transfer':token})
    assert response.status_code==409 and response.json()['detail']['code']=='kit_moved_or_unavailable'
    assert not kit.exists()


def test_replacement_at_old_location_is_not_the_same_kit(tmp_path,monkeypatch):
    kit,profile,_=managed(tmp_path,monkeypatch);api=TestClient(create_app())
    kit.rename(tmp_path/'Moved');kit.mkdir()
    assert api.get('/v1/configuration').status_code==409
    assert not list(kit.iterdir())

@pytest.mark.parametrize('mutation',[{'session_id':'bad'},{'kit_inode':True},{'data_directory':'/elsewhere'}, {'kit_directory':'relative'}])
def test_invalid_launch_context_cannot_redirect_storage(tmp_path,monkeypatch,mutation):
    _,profile,value=managed(tmp_path,monkeypatch);value.update(mutation);monkeypatch.setenv(ENVIRONMENT_KEY,json.dumps(value))
    with pytest.raises(ValueError):LaunchSession.from_environment()
    assert not profile.exists()


def test_stale_browser_cannot_write_equal_revision_of_another_fictitious_copy(tmp_path,monkeypatch):
    roots=[]
    for name,session in [('A','a'),('B','b')]:
        root=tmp_path/name;root.mkdir();profile=root/'DONNEES-PERSONNELLES/profil'
        value={'session_id':session*64,'kit_directory':str(root),'data_directory':str(profile),'kit_device':root.stat().st_dev,'kit_inode':root.stat().st_ino}
        monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(profile));monkeypatch.setenv(ENVIRONMENT_KEY,json.dumps(value))
        api=TestClient(create_app());roots.append((api,profile,value))
        if name=='A':
            old=api.get('/v1/configuration');assert old.status_code==200
    api,profile,value=roots[-1]
    before={str(p.relative_to(profile)):p.read_bytes() for p in profile.rglob('*') if p.is_file()}
    for supplied in [None,roots[0][2]['session_id']]:
        headers={'Origin':'http://testserver','X-NightMerit-Time-Authority':old.headers['X-NightMerit-Time-Authority']}
        if supplied:headers['X-NightMerit-Session']=supplied
        denied=api.put('/v1/configuration',json=old.json(),headers=headers)
        assert denied.status_code==409 and denied.json()['detail']['code']=='kit_session_changed'
    assert before=={str(p.relative_to(profile)):p.read_bytes() for p in profile.rglob('*') if p.is_file()}
    valid=api.get('/v1/configuration',headers={'Sec-Fetch-Mode':'cors','X-NightMerit-Session':value['session_id']})
    assert valid.status_code==200
    assert valid.json()['profile_revision']==old.json()['profile_revision']
    assert valid.headers['X-NightMerit-Session']==value['session_id']
    # A valid binding reaches request validation rather than a session refusal.
    accepted=api.put('/v1/configuration',json={},headers={'X-NightMerit-Session':value['session_id']})
    assert accepted.status_code==422


@pytest.mark.parametrize('headers',[{'Sec-Fetch-Mode':'cors'},{'X-NightMerit-Session':'b'*64},{'Origin':'http://testserver'}])
def test_managed_browser_reads_require_current_binding_but_diagnostics_survive(tmp_path,monkeypatch,headers):
    _,_,value=managed(tmp_path,monkeypatch);api=TestClient(create_app())
    denied=api.get('/v1/configuration',headers=headers)
    assert denied.status_code==409 and denied.json()['detail']['code']=='kit_session_changed'
    assert api.get('/v1/launcher-context',headers=headers).status_code==200
    assert api.get('/v1/data-context',headers=headers).status_code==200
    script=api.get('/ui/session-context.js')
    assert script.status_code==200 and value['session_id'] in script.text
    assert script.headers['Cache-Control']=='no-store'


def test_browser_storage_scope_survives_rename_but_differs_for_copied_kit(tmp_path,monkeypatch):
    kit,_,value=managed(tmp_path,monkeypatch);session=LaunchSession(**value)
    scope=session.storage_scope();moved=tmp_path/'Moved';kit.rename(moved)
    renamed=LaunchSession(**dict(value,kit_directory=str(moved),data_directory=str(moved/'DONNEES-PERSONNELLES/profil')))
    assert renamed.storage_scope()==scope
    kit.mkdir();value.update(kit_device=kit.stat().st_dev,kit_inode=kit.stat().st_ino)
    assert LaunchSession(**value).storage_scope()!=scope


def test_every_application_page_loads_binding_before_its_business_scripts():
    web=Path(__file__).resolve().parents[2]/'astropilot/web'
    for page in web.glob('*.html'):
        content=page.read_text()
        if page.name=='profile-transfer.html':
            assert '/ui/session-context.js' not in content
        elif '<script' in content:
            assert content.index('/ui/session-context.js') < content.index('</script>'),page.name
