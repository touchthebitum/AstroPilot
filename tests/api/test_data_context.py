"""Copy identification reads locations without interpreting or changing profiles."""
from pathlib import Path

from fastapi.testclient import TestClient
import astropilot.app as app_module
from astropilot.app import create_app


def test_data_context_distinguishes_copies_without_creating_or_loading_profiles(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Identifying a copy must not load business state or weather')
    client = TestClient(create_app(service_factory=forbidden, profile_provider=forbidden, weather_provider=forbidden))
    monkeypatch.setenv('ASTROPILOT_BUILD_COMMIT', '8843978')
    locations = [tmp_path / 'Copie personnelle été' / 'profil', tmp_path / 'Kit vierge' / 'profil']
    for location in locations:
        monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(location))
        result = client.get('/v1/data-context')
        assert result.status_code == 200
        assert result.headers['cache-control'] == 'no-store'
        assert result.json()['data_directory'] == str(location.absolute())
        assert result.json()['runtime']['build'] == '8843978'
        assert Path(result.json()['application_executable']).is_absolute()
        assert not location.exists()
    # A corrupt profile is never reset, interpreted as empty, or opened by this diagnostic.
    locations[1].mkdir(parents=True)
    profile = locations[1] / 'user_profile.json'
    profile.write_bytes(b'{invalid sentinel')
    before = profile.read_bytes()
    assert client.get('/v1/data-context').status_code == 200
    assert profile.read_bytes() == before
    assert list(locations[1].iterdir()) == [profile]
    assert str(tmp_path) not in client.get('/v1/runtime-identity').text


def test_data_context_unavailable_has_no_guessed_path(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    client = TestClient(create_app())
    def unavailable():
        raise OSError('private path must not leak in errors')
    monkeypatch.setattr(app_module, 'get_user_data_dir', unavailable)
    response = client.get('/v1/data-context')
    assert response.status_code == 503
    assert response.json() == {'detail': {'code': 'data_context_unavailable'}}
    assert not list(tmp_path.iterdir())
