from pathlib import Path
from datetime import datetime, timezone
import pytest
from astropilot import demo_mode

@pytest.fixture(autouse=True)
def inactive(monkeypatch):
    monkeypatch.setattr(demo_mode, '_active', False)

def test_demo_refuses_existing_real_profile(tmp_path):
    root = tmp_path / 'real';root.mkdir();original=b'{"personal":true}'
    (root/'user_profile.json').write_bytes(original)
    with pytest.raises(ValueError, match='déjà rempli'):
        demo_mode.prepare_profile(root)
    assert not demo_mode.context()['enabled']
    assert (root/'user_profile.json').read_bytes()==original
    assert not (root/demo_mode.MARKER).exists()

def test_demo_is_explicit_and_resumable(tmp_path, monkeypatch):
    monkeypatch.setenv('NIGHTMERIT_DEMO', '1')
    assert not demo_mode.context()['enabled']
    root=tmp_path/'demo';demo_mode.prepare_profile(root)
    assert demo_mode.context()['enabled']
    (root/'user_profile.json').write_text('{}')
    demo_mode.prepare_profile(root)
    assert (root/'user_profile.json').read_text()=='{}'

def test_simulated_weather_has_own_provider_and_current_dates(tmp_path, monkeypatch):
    import astro_score
    monkeypatch.setattr(astro_score.requests, 'get', lambda *a, **k: pytest.fail('Network forbidden in demo'))
    demo_mode.prepare_profile(tmp_path/'demo')
    weather=astro_score.fetch_weather(46.95,7.45)
    assert weather.provider==demo_mode.PROVIDER
    assert weather.valid_from <= datetime.now(timezone.utc) < weather.valid_until
    assert set(weather.payload['hourly']['cloud_cover'])=={0}
    assert set(weather.payload['hourly']['relative_humidity_2m'])=={50}
    assert weather.hour_count==192

def test_invalid_marker_and_relative_path_refused(tmp_path):
    with pytest.raises(ValueError):demo_mode.prepare_profile(Path('relative'))
    root=tmp_path/'bad';root.mkdir();(root/demo_mode.MARKER).write_text('{}')
    with pytest.raises(ValueError):demo_mode.prepare_profile(root)
    assert not demo_mode.context()['enabled']


@pytest.mark.parametrize('port', [18831,18837])
def test_occupied_port_does_not_create_profile_or_open_browser(tmp_path, monkeypatch,port):
    import socket
    root=tmp_path/'must-not-exist'
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(root))
    class BusySocket:
        def setsockopt(self, *args): pass
        def bind(self, address):
            assert address==('127.0.0.1',port)
            raise OSError('occupied')
        def close(self): pass
    monkeypatch.setattr(socket,'socket',lambda *a,**k:BusySocket())
    with pytest.raises(SystemExit, match='occupied'):demo_mode.main(port=port,open_browser=False)
    assert not root.exists()
    assert not demo_mode.context()['enabled']


def test_isolated_test_mode_requires_an_explicit_flag(monkeypatch):
    from astropilot import portable_entry
    calls=[]
    monkeypatch.setattr(demo_mode,'main',lambda **kw:calls.append(kw))
    monkeypatch.setattr('sys.argv',['AstroPilot','--demo-isolated-test-18837'])
    assert portable_entry.main()==0
    assert calls==[{'port':18837,'open_browser':False}]


def test_demo_refuses_other_ports_before_creating_profile(tmp_path,monkeypatch):
    root=tmp_path/'must-not-exist'
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(root))
    with pytest.raises(SystemExit,match='non autorisé'):demo_mode.main(port=8000)
    assert not root.exists()
