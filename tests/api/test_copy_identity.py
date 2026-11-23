"""Copy identity comes from launch provenance, not weather or restored projects."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot.profile_transfer_app import create_transfer_app
from astropilot.copy_identity import capture_copy_identity
from astropilot.launcher_context import LaunchSession


def managed(tmp_path,monkeypatch,kind):
    kit=tmp_path/'Copie été & essai';kit.mkdir();data=kit/'DONNEES-PERSONNELLES/profil'
    value={'session_id':'c'*64,'kit_directory':str(kit),'data_directory':str(data),
           'kit_device':kit.stat().st_dev,'kit_inode':kit.stat().st_ino}
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(data));monkeypatch.setenv('ASTROPILOT_LAUNCH_SESSION',json.dumps(value))
    if kind is None:monkeypatch.delenv('NIGHTMERIT_COPY_KIND',raising=False)
    else:monkeypatch.setenv('NIGHTMERIT_COPY_KIND',kind)
    return kit,data,LaunchSession(**value)


@pytest.mark.parametrize('assistant',[False,True])
@pytest.mark.parametrize('kind,label',[('fictitious','Essai fictif'),('personal','Personnel'),(None,'Copie non identifiée'),('invalid','Copie non identifiée')])
def test_explicit_copy_kind_is_readable_without_loading_profile_or_weather(tmp_path,monkeypatch,assistant,kind,label):
    kit,data,_=managed(tmp_path,monkeypatch,kind)
    def forbidden(*args,**kwargs):raise AssertionError('No weather or business reads for identity')
    app=(create_transfer_app(directory=data,origin='http://testserver') if assistant else
         create_app(service_factory=forbidden,profile_provider=forbidden,weather_provider=forbidden))
    before={str(p.relative_to(data)):p.read_bytes() for p in data.rglob('*') if p.is_file()}
    api=TestClient(app);reply=api.get('/ui/copy-identity.js')
    assert reply.status_code==200 and reply.headers['cache-control']=='no-store'
    payload=json.loads(reply.text.split('=',1)[1].split(';\n',1)[0])
    assert payload['label']==label and payload['name']==kit.name
    assert payload['kind']==(kind if kind in {'personal','fictitious'} else 'unidentified')
    assert '/ui/copy-identity.js' in api.get('/').text
    if not assistant:assert api.get('/v1/data-context').json()['copy_identity']==payload
    assert before=={str(p.relative_to(data)):p.read_bytes() for p in data.rglob('*') if p.is_file()}


@pytest.mark.parametrize('weather',['real','simulated','unavailable'])
def test_kind_does_not_depend_on_weather_or_restored_documents(tmp_path,monkeypatch,weather):
    _,data,session=managed(tmp_path,monkeypatch,'fictitious')
    import astropilot.demo_mode as demo_mode
    monkeypatch.setattr(demo_mode,'_active',weather=='simulated')
    assert capture_copy_identity(session)['label']=='Essai fictif'
    app=create_app();api=TestClient(app);before=api.get('/v1/data-context').json()['copy_identity']
    assert api.get('/v1/demo-context').json()['weather']==('simulated' if weather=='simulated' else 'real')
    # Even unreadable/restored documents must not change a copy's classification.
    data.mkdir(parents=True,exist_ok=True);p=data/'user_profile.json';p.write_text('{unreadable sentinel')
    monkeypatch.setenv('NIGHTMERIT_COPY_KIND','personal')
    assert api.get('/v1/data-context').json()['copy_identity']==before
    assert p.read_text()=='{unreadable sentinel'


def test_kind_without_managed_launcher_is_unknown(monkeypatch):
    monkeypatch.setenv('NIGHTMERIT_COPY_KIND','personal')
    assert capture_copy_identity(None)=={'kind':'unidentified','label':'Copie non identifiée','name':None}


def test_every_page_keeps_identity_outside_screen_navigation():
    web=Path(__file__).resolve().parents[2]/'astropilot/web'
    for page in web.glob('*.html'):
        assert page.read_text().count('/ui/copy-identity.js')==1,page.name
    script=(web/'copy-identity.js').read_text()
    assert 'document.body.prepend(banner)' in script
    assert 'textContent' in script and 'innerHTML' not in script
    assert 'fetch(' not in script and 'localStorage' not in script


@pytest.mark.parametrize("assistant", [False, True])
def test_explicit_demo_runtime_identifies_fictitious_copy_without_managed_session(monkeypatch, tmp_path, assistant):
    monkeypatch.delenv('ASTROPILOT_LAUNCH_SESSION', raising=False)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path / 'fictitious'))
    monkeypatch.setenv('NIGHTMERIT_COPY_KIND', 'personal')
    import astropilot.demo_mode as demo_mode
    monkeypatch.setattr(demo_mode, '_active', True)
    app = create_transfer_app(directory=tmp_path / 'fictitious', origin='http://testserver', demo=True) if assistant else create_app()
    response = TestClient(app).get('/ui/copy-identity.js')
    assert response.status_code == 200
    identity = json.loads(response.text.split('=', 1)[1].split(';\n', 1)[0])
    assert identity == {'kind': 'demonstration', 'label': 'Essai fictif — météo simulée',
                        'name': 'Démonstration locale — données fictives uniquement'}
    assert not (tmp_path / 'fictitious' / 'user_profile.json').exists()
