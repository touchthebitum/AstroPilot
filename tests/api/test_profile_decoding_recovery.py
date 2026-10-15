"""Real malformed files must use explicit, lossless configuration recovery."""
import errno

import pytest
from fastapi.testclient import TestClient

from astropilot.app import create_app
from astropilot import user_profile


@pytest.fixture(params=[b'\xff\xfeprivate', b'[' * 10000 + b'0' + b']' * 10000, b'{"value":' + b'1' * 10000 + b'}'],
                ids=['invalid-utf8', 'deep-json', 'huge-integer'])
def malformed(request):
    return request.param


def test_malformed_profile_explicit_recovery(tmp_path, monkeypatch, malformed):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    client = TestClient(create_app())
    # A healthy snapshot comes through the real write boundary, not hand-built JSON.
    payload = {'site': {'name': 'Test', 'latitude': 47.1035, 'longitude': 6.8328, 'bortle': 4},
               'equipment': {'preset_id': 'samyang_183'}, 'projects': {}}
    assert client.put('/v1/configuration', json=payload).status_code == 200
    path = tmp_path / 'user_profile.json'
    healthy = path.read_bytes()
    projection = client.get('/v1/configuration').json()
    sentinel = tmp_path / 'unrelated-history.bin'
    sentinel.write_bytes(b'unchanged history')
    path.write_bytes(malformed)

    response = client.get('/v1/configuration')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'configuration_corrupt'
    assert path.read_bytes() == malformed
    assert not list(tmp_path.glob('.user_profile.corrupt.*.json'))
    assert client.post('/v1/configuration/recover').status_code == 200
    quarantine, = tmp_path.glob('.user_profile.corrupt.*.json')
    assert quarantine.read_bytes() == malformed
    assert not path.exists()
    assert client.post('/v1/configuration/recover').status_code == 200
    assert list(tmp_path.glob('.user_profile.corrupt.*.json')) == [quarantine]
    # Explicitly restore the known healthy copy; a fresh app rereads it unchanged.
    path.write_bytes(healthy)
    restarted = TestClient(create_app())
    for _ in range(2):
        assert restarted.get('/v1/configuration').json() == projection
        assert restarted.post('/v1/configuration/recover').status_code == 409
        assert path.read_bytes() == healthy
        assert sentinel.read_bytes() == b'unchanged history'
        assert quarantine.read_bytes() == malformed


def test_malformed_profile_write_is_refused(tmp_path, monkeypatch, malformed):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    path = tmp_path / 'user_profile.json'
    candidate = {'active_equipment': 'samyang_183', 'available_equipment': ['samyang_183'],
                 'projects': {}, 'sessions': []}
    path.write_bytes(malformed)
    with pytest.raises(user_profile.UserProfileError):
        user_profile.load_user_profile()
    with pytest.raises(user_profile.PersistedProfileCorruptError):
        user_profile.save_user_profile(candidate)
    assert path.read_bytes() == malformed
    assert not list(tmp_path.glob('.user_profile.*.tmp'))
    assert not list(tmp_path.glob('.user_profile.corrupt.*.json'))


@pytest.mark.parametrize('code', [errno.EACCES, errno.EIO])
def test_profile_io_failure_is_never_quarantined(tmp_path, monkeypatch, code):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    path = tmp_path / 'user_profile.json'
    original = b'{broken'
    path.write_bytes(original)
    real_open = user_profile.Path.open
    def fail_open(target, *args, **kwargs):
        if target == path:
            raise OSError(code, 'synthetic read failure')
        return real_open(target, *args, **kwargs)
    monkeypatch.setattr(user_profile.Path, 'open', fail_open)
    with pytest.raises(OSError):
        user_profile.quarantine_corrupt_user_profile(validate_configuration=lambda value: value)
    monkeypatch.setattr(user_profile.Path, 'open', real_open)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('.user_profile.corrupt.*.json'))


def test_malformed_profile_direct_recovery(tmp_path, monkeypatch, malformed):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    path = tmp_path / 'user_profile.json'
    path.write_bytes(malformed)
    client = TestClient(create_app())
    assert client.post('/v1/configuration/recover').status_code == 200
    quarantine, = tmp_path.glob('.user_profile.corrupt.*.json')
    assert quarantine.read_bytes() == malformed
    assert not path.exists()
