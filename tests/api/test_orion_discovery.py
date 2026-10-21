"""Real synthetic-weather Orion preselection through explicit mission acceptance."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.target_discovery import TARGET_IMAGES
from decision.weather.weather_ingress import validate_weather_payload
from test_target_discovery import HA, profile, request
from test_clean_machine_all_night_regression import _weather_snapshot

REF = datetime(2026, 12, 9, 18, tzinfo=timezone.utc)


def winter_weather(*, clouds=20):
    payload = deepcopy(_weather_snapshot(reference_time=REF).payload)
    shift = int((REF - datetime(2026, 8, 29, 18, tzinfo=timezone.utc)).total_seconds())
    payload['hourly']['time'] = [value + shift for value in payload['hourly']['time']]
    payload['hourly']['cloud_cover'] = [clouds] * len(payload['hourly']['time'])
    # December in Zurich is UTC+1; hourly timestamps are absolute Unix instants.
    payload['utc_offset_seconds'] = 3600
    return validate_weather_payload(payload, requested_latitude=46.888,
        requested_longitude=6.55, requested_timezone='Europe/Zurich',
        retrieved_at_utc=REF - timedelta(minutes=5))


def test_orion_discovery_to_accepted_mission_does_not_invent_progress(tmp_path, monkeypatch):
    from astro_score import build_durable_tonight_application_service
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    weather = winter_weather()
    saved = profile()
    before = deepcopy(saved)
    discovery = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: weather, clock=lambda: REF))
    response = discovery.post('/v1/target-suggestions', json=request())
    assert response.status_code == 200, response.text
    proposal = next(item for item in response.json()['suggestions'] if item['catalog_key'] == 'M42')
    assert proposal['imaging_field_id'] == 'm42'
    assert proposal['acquisition_intent_id'] == 'm42_ha'
    assert proposal['filter']['filter_profile_id'] == HA
    assert proposal['equipment_match']['framing']['status'] == 'nominal_fit'
    assert 'saturé' in proposal['guidance']['advice']
    assert 'plus serrée' in proposal['image']['note']
    assert saved == before
    assert not list(tmp_path.rglob('*.json'))
    image = discovery.get(proposal['image']['src'])
    assert image.status_code == 200
    assert image.headers['content-type'] == 'image/jpeg'
    assert image.content[:2] == b'\xff\xd8'

    def factory():
        service = build_durable_tonight_application_service()
        service.clock = lambda: REF  # the same synthetic clock for acceptance freshness
        return service

    live = TestClient(create_app(service_factory=factory,
        weather_provider=lambda *args: weather, clock=lambda: REF))
    project = {'hours': 0, 'target_hours': 3, 'imaging_field_id': proposal['imaging_field_id'],
        'acquisition_intent_targets': [{'acquisition_intent_id': proposal['acquisition_intent_id'], 'target_hours': 3}],
        'acquisition_intent_progress': [{'acquisition_intent_id': proposal['acquisition_intent_id'], 'acquired_duration_manual': 0}]}
    response = live.put('/v1/configuration', json={
        'site': {'name': 'Synthetic', 'latitude': 46.888, 'longitude': 6.55, 'bortle': 4},
        'equipment': {'preset_id': 'samyang_183'}, 'projects': {'M42': project}})
    assert response.status_code == 200, response.text
    decision = live.post('/v1/tonight', json={'availability': {'mode': 'all_night'}})
    assert decision.status_code == 200, decision.text
    decision = decision.json()
    assert decision['status'] == 'available'
    assert decision['catalog_key'] == 'M42'
    assert decision['selected_acquisition_intent_id'] == 'm42_ha'
    assert live.get('/v1/accepted-mission/current').json() is None
    accepted = live.post('/v1/decision-selections', json={
        'acceptance_request_id': 'orion-synthetic-acceptance', 'decision_id': decision['decision_id'],
        'source': 'primary_recommendation', 'selected_catalog_key': 'M42',
        'acquisition_intent_id': 'm42_ha', 'selected_at': REF.isoformat()})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'accepted'
    mission = live.get('/v1/accepted-mission/current').json()
    assert mission is not None
    assert live.get('/v1/configuration').json()['projects']['M42']['hours'] == 0
    assert live.get(f"/v1/missions/{mission['mission_id']}/executions").json() == []


@pytest.mark.parametrize('clouds,filters,availability', [
    (100, [HA], {'mode': 'all_night'}),
    (20, ['baader_oiii_highspeed_6_5nm'], {'mode': 'all_night'}),
    (20, [HA], {'mode': 'fixed_window', 'start': '2026-12-09T23:00:00+01:00',
               'end': '2026-12-09T23:20:00+01:00'}),
])
def test_orion_is_not_offered_when_conditions_do_not_allow_it(tmp_path, monkeypatch, clouds, filters, availability):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    client = TestClient(create_app(profile_provider=profile,
        weather_provider=lambda *args: winter_weather(clouds=clouds), clock=lambda: REF))
    response = client.post('/v1/target-suggestions', json=request(
        confirmed_filter_profile_ids=filters, availability=availability))
    assert response.status_code == 200, response.text
    assert not response.json()['suggestions']
    assert not list(tmp_path.rglob('*.json'))


def test_all_discovery_templates_have_licensed_images_and_exact_intent_help():
    from astropilot.project_templates import project_templates
    templates = [item for item in project_templates() if item['discovery_supported']]
    assert {item['catalog_key'] for item in templates} == set(TARGET_IMAGES)
    for template in templates:
        image = TARGET_IMAGES[template['catalog_key']]
        assert image['credit'] and image['source_url'].startswith('https://')
        assert image['license_url'] == 'https://creativecommons.org/licenses/by/4.0/'
        assert template['guidance']['source_url'].startswith('https://')
        for intent in template['acquisition_intents']:
            assert all(intent['guidance'][key] for key in ('difficulty', 'purpose', 'advice'))
            assert intent['filter_type'] == 'Ha'
