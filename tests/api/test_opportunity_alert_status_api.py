from datetime import datetime, timezone
from fastapi.testclient import TestClient
from astropilot.app import create_app
from astropilot.opportunity_alert_status import StatusObserver


def test_get_is_read_only_and_does_not_evaluate(tmp_path, monkeypatch):
    directory = tmp_path / 'user'
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(directory))
    def forbidden(*a, **k):
        raise AssertionError('business operation invoked')
    app = create_app(service_factory=forbidden, weather_provider=forbidden,
                     profile_provider=forbidden, alert_ledger_factory=forbidden)
    with TestClient(app) as client:
        response = client.get('/v1/opportunity-alerts/status')
        assert response.json() == {'state': 'unknown'}
        assert response.headers['cache-control'] == 'no-store'
        assert not directory.exists()
        directory.mkdir()
        obs = StatusObserver(directory)
        obs.start(enabled=False, channel='windows', interval_seconds=60)
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        response = client.get('/v1/opportunity-alerts/status')
        assert response.json()['enabled'] is False
        assert response.json()['channel'] == 'windows'
        assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
        assert client.post('/v1/opportunity-alerts/status').status_code == 405


def test_api_rejects_lab_without_writing(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    (tmp_path / '.field_lab_namespace').write_text('{}')
    with TestClient(create_app(service_factory=lambda: None)) as client:
        assert client.get('/v1/opportunity-alerts/status').json() == {'state': 'unavailable'}
    assert {p.name for p in tmp_path.iterdir()} == {'.field_lab_namespace'}
