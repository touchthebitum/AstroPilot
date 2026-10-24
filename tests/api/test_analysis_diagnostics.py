import json
import logging

import pytest
from fastapi.testclient import TestClient

import astropilot.analysis_diagnostics as diagnostics
from astropilot.app import create_app
from decision.services.tonight_application_service import TonightResult, TonightStatus
from tests.api.test_tonight_api import DEFAULT_WEATHER, DEFAULT_WEATHER_REFERENCE_TIME, valid_profile


@pytest.mark.parametrize('failure', [None, 'weather', 'calculation'])
def test_analysis_times_separate_network_and_calculation_without_private_data(monkeypatch, caplog, failure):
    elapsed = [0.0]
    monkeypatch.setattr(diagnostics, 'perf_counter', lambda: elapsed[0])
    logger = logging.getLogger('astropilot.launcher.analysis')
    logger.addHandler(caplog.handler)
    original = logger.propagate
    logger.propagate = False
    calls = []
    def weather(lat, lon):
        elapsed[0] += 2
        calls.append('weather')
        return None if failure == 'weather' else DEFAULT_WEATHER
    class Service:
        def evaluate(self, **kwargs):
            elapsed[0] += 3
            calls.append('calculation')
            if failure == 'calculation':
                raise RuntimeError('SECRET https://private.invalid?latitude=46.7508')
            return TonightResult(None, None, None, status=TonightStatus.NO_NIGHT)
    try:
        client = TestClient(create_app(service_factory=lambda: Service(),
            weather_provider=weather, profile_provider=valid_profile,
            clock=lambda: DEFAULT_WEATHER_REFERENCE_TIME), raise_server_exceptions=False)
        response = client.post('/v1/tonight', json={})
        assert response.status_code == {None:200, 'weather':503, 'calculation':500}[failure]
        records = [json.loads(x.message.split('analysis_diagnostic ',1)[1])
                   for x in caplog.records if x.message.startswith('analysis_diagnostic ')]
        assert len(records) == 1
        record = records[0]
        assert record['http_status'] == response.status_code
        assert record['duration_ms']['weather'] == 2000
        if failure == 'weather':
            assert calls == ['weather']
            assert record['duration_ms']['total'] == 2000
            assert 'calculation' not in record['duration_ms']
        else:
            assert calls == ['weather', 'calculation']
            assert record['duration_ms']['total'] == 5000
            assert record['duration_ms']['calculation'] == 3000
        if failure != 'calculation':
            assert response.headers[diagnostics.HEADER] == record['diagnostic_id']
            assert response.headers['X-Weather-Diagnostic-ID'] == record['diagnostic_id']
            assert 'weather;dur=2000.000' in response.headers['Server-Timing']
        text = json.dumps(record)
        assert not any(secret in text for secret in ['SECRET', 'private.invalid', '46.7508', 'Buttes'])
    finally:
        logger.removeHandler(caplog.handler)
        logger.propagate = original
