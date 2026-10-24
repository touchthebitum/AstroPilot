"""Whole H II fields keep separate intents and preserve historical project aliases."""
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.project_templates import project_templates
from decision.definitions.production_imaging_fields import build_production_imaging_field_resolver
from test_target_discovery import HA, profile, request
from test_orion_discovery import REF, winter_weather

# An early-evening window gives these northern regions priority; Orion and
# Rosette are lower then. This uses the real ranking, not a forced candidate.
AVAILABILITY = {'mode': 'fixed_window', 'start': '2026-12-09T19:00:00+01:00',
                'end': '2026-12-09T21:00:00+01:00'}


@pytest.mark.parametrize('key,field,extent', [('IC1805', 'sh2-190', 150), ('IC1848', 'sh2-199', 120)])
def test_whole_region_discovery_to_explicit_mission(tmp_path, monkeypatch, key, field, extent):
    from astro_score import build_durable_tonight_application_service
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    saved = profile()
    before = deepcopy(saved)
    weather = winter_weather()
    discovery = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: weather, clock=lambda: REF))
    response = discovery.post('/v1/target-suggestions', json=request(availability=AVAILABILITY))
    assert response.status_code == 200, response.text
    suggestions = response.json()['suggestions']
    assert len(suggestions) <= 3
    proposal = next(item for item in suggestions if item['catalog_key'] == key)
    assert proposal['imaging_field_id'] == field
    assert proposal['acquisition_intent_id'] == field + '_ha'
    assert proposal['equipment_match']['extent_arcmin'] == extent
    assert proposal['equipment_match']['framing']['status'] == 'nominal_fit'
    assert proposal['filter']['filter_profile_id'] == HA
    assert not proposal['already_saved']
    assert proposal['existing_project_key'] is None
    assert 'seulement cette région' in proposal['image']['note']
    assert proposal['image']['license_label'] == 'CC BY-SA 4.0'
    assert proposal['image']['license_url'] == 'https://creativecommons.org/licenses/by-sa/4.0/'
    image = discovery.get(proposal['image']['src'])
    assert image.status_code == 200 and image.headers['content-type'] == 'image/jpeg'
    assert image.content == (Path(__file__).parents[2] / 'astropilot/web/target-heart-soul-ha.jpg').read_bytes()
    assert saved == before
    assert not list(tmp_path.rglob('*.json'))

    def factory():
        service = build_durable_tonight_application_service()
        service.clock = lambda: REF
        return service

    live = TestClient(create_app(service_factory=factory,
        weather_provider=lambda *args: weather, clock=lambda: REF))
    project = {'hours': 0, 'target_hours': 3, 'imaging_field_id': field,
        'acquisition_intent_targets': [{'acquisition_intent_id': field + '_ha', 'target_hours': 3}],
        'acquisition_intent_progress': [{'acquisition_intent_id': field + '_ha', 'acquired_duration_manual': 0}]}
    response = live.put('/v1/configuration', json={
        'site': {'name': 'Synthetic', 'latitude': 46.888, 'longitude': 6.55, 'bortle': 4},
        'equipment': {'preset_id': 'samyang_183'}, 'projects': {key: project}})
    assert response.status_code == 200, response.text
    response = live.post('/v1/tonight', json={'availability': AVAILABILITY})
    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision['status'] == 'available', decision
    assert decision['catalog_key'] == key
    assert decision['selected_acquisition_intent_id'] == field + '_ha'
    assert live.get('/v1/accepted-mission/current').json() is None
    wrong_intent = 'sh2-199_ha' if field == 'sh2-190' else 'sh2-190_ha'
    selection = {'acceptance_request_id': 'heart-soul-' + key, 'decision_id': decision['decision_id'],
        'source': 'primary_recommendation', 'selected_catalog_key': key,
        'acquisition_intent_id': field + '_ha', 'selected_at': REF.isoformat()}
    rejected = live.post('/v1/decision-selections', json={**selection,
        'acceptance_request_id': 'wrong-' + key, 'acquisition_intent_id': wrong_intent})
    assert rejected.status_code == 409
    assert live.get('/v1/accepted-mission/current').json() is None
    accepted = live.post('/v1/decision-selections', json=selection)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'accepted'
    mission = live.get('/v1/accepted-mission/current').json()
    assert mission['mission_id'] == accepted.json()['mission_id']
    assert live.get(f"/v1/missions/{mission['mission_id']}/executions").json() == []
    assert live.get('/v1/configuration').json()['projects'][key]['hours'] == 0


@pytest.mark.parametrize('alias,key', [('Heart', 'IC1805'), ('Soul', 'IC1848')])
def test_existing_alias_is_retrieved_without_migrating_or_overwriting(tmp_path, monkeypatch, alias, key):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    saved = profile()
    saved['projects'] = {alias: {'hours': 7, 'target_hours': 15}}
    before = deepcopy(saved)
    client = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: winter_weather(), clock=lambda: REF))
    response = client.post('/v1/target-suggestions', json=request(availability=AVAILABILITY))
    assert response.status_code == 200, response.text
    proposal = next(item for item in response.json()['suggestions'] if item['catalog_key'] == key)
    assert proposal['already_saved']
    assert proposal['existing_project_key'] == alias
    assert saved == before
    assert not list(tmp_path.rglob('*.json'))


def test_ambiguous_saved_aliases_are_not_guessed(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    saved = profile()
    saved['projects'] = {'Heart': {'hours': 1}, 'IC1805': {'hours': 2}}
    before = deepcopy(saved)
    client = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: winter_weather(), clock=lambda: REF))
    response = client.post('/v1/target-suggestions', json=request(availability=AVAILABILITY))
    assert response.status_code == 200, response.text
    assert 'IC1805' not in {item['catalog_key'] for item in response.json()['suggestions']}
    assert saved == before


def test_whole_nebula_definitions_do_not_duplicate_the_legacy_aliases():
    templates = project_templates()
    assert sum(item['catalog_key'] in {'IC1805', 'Heart'} for item in templates) == 1
    assert sum(item['catalog_key'] in {'IC1848', 'Soul'} for item in templates) == 1
    resolver = build_production_imaging_field_resolver()
    for field, key in [('sh2-190', 'IC1805'), ('sh2-199', 'IC1848')]:
        obj = resolver.resolve_object(field)
        assert obj.canonical_name == key
        assert obj.object_subtype == 'H II region'
        assert resolver.resolve(field).components[0].celestial_object_id == field
