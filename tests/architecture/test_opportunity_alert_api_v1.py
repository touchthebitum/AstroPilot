from dataclasses import replace
from datetime import timedelta, timezone

import pytest
from fastapi import HTTPException

from test_opportunity_alerts_v1 import complete, policy
from test_modern_mission_authorization import assembly_environment, START
from astropilot.opportunity_alert_api import claim_opportunity_alert
from astropilot.opportunity_alert_ledger import FileOpportunityAlertLedger
from decision.models.opportunity_alert import OpportunityAlertPolicy


def transport(result, policy, directory, at=START):
    return claim_opportunity_alert(result=result, policy=policy,
        ledger=FileOpportunityAlertLedger(directory), logical_time=at).model_dump(mode='json')


def test_disabled(complete, tmp_path):
    payload = transport(complete, OpportunityAlertPolicy(), tmp_path)
    assert payload['status'] == 'no_alert'
    assert payload['reason_codes'] == ['alerts_disabled']
    assert payload['alert'] is None
    assert not (tmp_path / 'opportunity_alert_ledger.json').exists()


def test_alert_then_restart_suppression(complete, policy, tmp_path):
    payload = transport(complete, policy, tmp_path)
    assert payload['status'] == 'alert'
    alert = payload['alert']
    assert set(alert) == {'alert_id', 'project_key', 'imaging_field_id',
        'acquisition_intent_id', 'site', 'window_start', 'window_end',
        'duration_minutes', 'expected_gain', 'decision_score', 'logical_time'}
    assert alert['expected_gain'] == complete.mission.expected_gain
    assert alert['decision_score'] == complete.mission.astro_quality.decision_score
    assert alert['window_start'].endswith('Z')
    assert alert['logical_time'].endswith('Z')
    assert transport(complete, policy, tmp_path)['reason_codes'] == ['duplicate_or_cooldown']
    # Even after rebuilding the file ledger, no replay can emit again.
    assert transport(complete, policy, tmp_path)['status'] == 'no_alert'


def test_corrupt_ledger_http_error(complete, policy, tmp_path):
    path = tmp_path / 'opportunity_alert_ledger.json'
    path.write_text('{broken')
    with pytest.raises(HTTPException) as error:
        transport(complete, policy, tmp_path)
    assert error.value.status_code == 503
    assert error.value.detail == {'code': 'opportunity_alert_ledger_unavailable'}
    assert path.read_text() == '{broken'


@pytest.mark.parametrize('damage', ['legacy', 'availability', 'partial_aqi', 'intent', 'evidence'])
def test_no_alert_for_missing_evidence(complete, policy, tmp_path, damage):
    if damage == 'legacy':
        complete = replace(complete, alert_live_marker=None)
    elif damage == 'availability':
        complete = replace(complete, alert_mission_input=replace(complete.alert_mission_input, availability=None))
    elif damage == 'partial_aqi':
        complete = replace(complete, mission=replace(complete.mission,
            astro_quality=replace(complete.mission.astro_quality, decision_eligible=False)))
    elif damage == 'intent':
        policy = replace(policy, filter_profile_ids=('other',))
    else:
        complete = replace(complete, forecast_evidence=None)
    assert transport(complete, policy, tmp_path)['status'] == 'no_alert'


def test_utc_and_internal_fidelity(complete, policy, tmp_path):
    from decision.services.opportunity_alert_service import OpportunityAlertService, InMemoryOpportunityAlertLedger
    internal = OpportunityAlertService(InMemoryOpportunityAlertLedger()).evaluate(
        result=complete, policy=policy, logical_time=START).alert
    payload = transport(complete, policy, tmp_path, START.astimezone(timezone(timedelta(hours=2))))
    alert = payload['alert']
    assert alert['alert_id'] == internal.idempotency_key
    assert alert['duration_minutes'] == internal.duration_minutes
    assert alert['project_key'] == internal.project_key
    assert alert['logical_time'] == START.isoformat().replace('+00:00', 'Z')


def test_http_adapter_corruption_and_suppression(complete, policy, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from astropilot.opportunity_alert_api import OpportunityAlertResponse
    app = FastAPI()
    @app.post('/claim', response_model=OpportunityAlertResponse)
    def claim():
        return claim_opportunity_alert(result=complete, policy=policy,
            ledger=FileOpportunityAlertLedger(tmp_path), logical_time=START)
    client = TestClient(app)
    assert client.post('/claim').json()['status'] == 'alert'
    assert client.post('/claim').json()['status'] == 'no_alert'
    path = tmp_path / 'opportunity_alert_ledger.json'
    path.write_text('{broken')
    response = client.post('/claim')
    assert response.status_code == 503
    assert response.json() == {'detail': {'code': 'opportunity_alert_ledger_unavailable'}}


def test_real_tonight_http_claim(complete, policy, tmp_path):
    from fastapi.testclient import TestClient
    from astropilot.app import create_app
    from decision.weather.weather_ingress import WeatherSnapshot
    calls = []
    class Service:
        def evaluate(self, **kwargs):
            calls.append(kwargs)
            return complete
    weather = WeatherSnapshot(payload={'hourly': {}}, provider='Open-Meteo',
        retrieved_at_utc=START, requested_latitude=46.75, requested_longitude=6.55,
        grid_latitude=46.75, grid_longitude=6.55, grid_distance_km=0., elevation_m=800.,
        timezone='Europe/Zurich', timezone_source='coordinates_local', utc_offset_seconds=7200,
        valid_from=START, valid_until=START + timedelta(days=1), hour_count=24, completeness=1.)
    client = TestClient(create_app(service_factory=Service,
        weather_provider=lambda *args: weather,
        profile_provider=lambda: {'location': {'name': 'Buttes', 'latitude': 46.75, 'longitude': 6.55},
            'preferences': {'bortle': 4}, 'active_equipment': 'samyang_183', 'available_equipment': ['samyang_183']},
        clock=lambda: START, alert_policy_provider=lambda: policy,
        alert_ledger_factory=lambda: FileOpportunityAlertLedger(tmp_path)))
    response = client.post('/v1/tonight', json={'claim_opportunity_alert': True})
    assert response.status_code == 200, response.text
    assert response.json()['opportunity_alert']['status'] == 'alert'
    assert len(calls) == 1
    response = client.post('/v1/tonight', json={'claim_opportunity_alert': True})
    assert response.json()['opportunity_alert']['reason_codes'] == ['duplicate_or_cooldown']
    (tmp_path / 'opportunity_alert_ledger.json').write_text('{broken')
    response = client.post('/v1/tonight', json={'claim_opportunity_alert': True})
    assert response.status_code == 503
    assert response.json() == {'detail': {'code': 'opportunity_alert_ledger_unavailable'}}


@pytest.mark.parametrize('value', ['true', 1, None])
def test_claim_requires_explicit_boolean(value):
    from astropilot.app import TonightRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TonightRequest(claim_opportunity_alert=value)
