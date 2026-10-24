"""Seasonal end-to-end checks with synthetic weather, never operator field evidence."""
from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astropy.coordinates import SkyCoord, FK4
from astropy.time import Time
import astropy.units as u
from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.project_templates import project_templates
from astropilot.target_catalogue import canonical_target
from decision.definitions.production_extended_targets import EXTENDED_HA_TARGETS
from decision.weather.weather_ingress import validate_weather_payload
from test_clean_machine_all_night_regression import _weather_snapshot
from test_target_discovery import HA, profile, request

CASES = [('M16', 7, 10, 35.0), ('M17', 7, 10, 35.0),
    ('NGC1499', 11, 9, 46.888), ('IC5070', 8, 29, 46.888),
    ('IC434', 12, 9, 46.888), ('Sh2-296', 1, 20, 46.888),
    ('NGC3372', 3, 20, -33.0), ('IC4628', 6, 10, -33.0)]


def weather_for(ref, latitude=46.888, clouds=10):
    base = datetime(2026, 8, 29, 18, tzinfo=timezone.utc)
    payload = deepcopy(_weather_snapshot(reference_time=base).payload)
    shift = int((ref - base).total_seconds())
    payload['hourly']['time'] = [value + shift for value in payload['hourly']['time']]
    payload['hourly']['cloud_cover'] = [clouds] * len(payload['hourly']['time'])
    payload['latitude'] = latitude
    payload['longitude'] = 6.55
    payload['utc_offset_seconds'] = 0
    payload['timezone'] = 'UTC'
    return validate_weather_payload(payload, requested_latitude=latitude,
        requested_longitude=6.55, requested_timezone='UTC',
        retrieved_at_utc=ref - timedelta(minutes=5))


@pytest.mark.parametrize('key,month,day,latitude', CASES)
def test_each_new_field_can_be_physically_preselected_and_explicitly_accepted(
        tmp_path, monkeypatch, key, month, day, latitude):
    from astro_score import build_durable_tonight_application_service
    import astropilot.target_discovery as discovery_module
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    ref = datetime(2026, month, day, 18, tzinfo=timezone.utc)
    weather = weather_for(ref, latitude)
    saved = profile()
    saved['location'].update(latitude=latitude, timezone='UTC')
    before = deepcopy(saved)
    # Isolate registry membership only; retain the actual full sky ranking,
    # weather, geometry, material and productive-window evaluation.
    template = next(t for t in project_templates() if t['catalog_key'] == key)
    monkeypatch.setattr(discovery_module, 'project_templates', lambda: [template])
    client = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: weather, clock=lambda: ref))
    response = client.post('/v1/target-suggestions', json=request())
    assert response.status_code == 200, response.text
    suggestions = response.json()['suggestions']
    assert len(suggestions) == 1, response.json()
    proposal = suggestions[0]
    assert proposal['catalog_key'] == key
    intent = template['imaging_field_id'] + '_ha'
    assert proposal['acquisition_intent_id'] == intent
    assert proposal['filter']['filter_profile_id'] == HA
    assert proposal['equipment_match']['framing']['status'] == 'nominal_fit'
    assert saved == before
    assert not list(tmp_path.rglob('*.json'))
    assert client.get(proposal['image']['src']).content[:2] == b'\xff\xd8'

    def factory():
        service = build_durable_tonight_application_service()
        service.clock = lambda: ref
        return service

    live = TestClient(create_app(service_factory=factory,
        weather_provider=lambda *args: weather, clock=lambda: ref))
    project = {'hours': 0, 'target_hours': 3, 'imaging_field_id': template['imaging_field_id'],
        'acquisition_intent_targets': [{'acquisition_intent_id': intent, 'target_hours': 3}],
        'acquisition_intent_progress': [{'acquisition_intent_id': intent, 'acquired_duration_manual': 0}]}
    config = live.put('/v1/configuration', json={'site': {'name': 'Synthetic',
        'latitude': latitude, 'longitude': 6.55, 'bortle': 4},
        'equipment': {'preset_id': 'samyang_183'}, 'projects': {key: project}})
    assert config.status_code == 200, config.text
    decision_response = live.post('/v1/tonight', json={'availability': {'mode': 'all_night'},
        'selected_project_id': key})
    assert decision_response.status_code == 200, decision_response.text
    decision = decision_response.json()
    assert decision['status'] == 'available', decision
    assert decision['catalog_key'] == key
    selection = {'acceptance_request_id': 'expanded-' + key,
        'decision_id': decision['decision_id'], 'source': 'primary_recommendation',
        'selected_catalog_key': key, 'acquisition_intent_id': intent,
        'selected_at': ref.isoformat()}
    wrong = live.post('/v1/decision-selections', json={**selection,
        'acceptance_request_id': 'wrong-' + key, 'acquisition_intent_id': 'ou4_oiii'})
    assert wrong.status_code == 409
    accepted = live.post('/v1/decision-selections', json=selection)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'accepted'
    assert live.get('/v1/configuration').json()['projects'][key]['hours'] == 0
    mission = live.get('/v1/accepted-mission/current').json()
    assert live.get(f"/v1/missions/{mission['mission_id']}/executions").json() == []


def test_catalogue_coordinates_and_extents_match_pinned_originals():
    path = Path(__file__).parents[2] / 'astropilot/catalogue_data/NGC.csv'
    with path.open() as stream:
        rows = {r['Name']: r for r in csv.DictReader(stream, delimiter=';')}
    for target in EXTENDED_HA_TARGETS:
        if target['extent_source'] != 'openngc':
            continue
        source = rows[target['source_row']]
        coord = SkyCoord(source['RA'], source['Dec'], unit=(u.hourangle, u.deg))
        assert target['ra'] == pytest.approx(coord.ra.deg, abs=1e-8)
        assert target['dec'] == pytest.approx(coord.dec.deg, abs=1e-8)
        assert target['extent'] == float(source['MajAx'])
    seagull = next(t for t in EXTENDED_HA_TARGETS if t['key'] == 'Sh2-296')
    icrs = SkyCoord(105.8625*u.deg, -11.141388888888889*u.deg,
        frame=FK4(equinox=Time('B1950.0'))).icrs
    assert seagull['ra'] == pytest.approx(icrs.ra.deg, abs=1e-8)
    assert seagull['dec'] == pytest.approx(icrs.dec.deg, abs=1e-8)
    assert canonical_target('NGC1499').extent_arcmin == 160  # not Sh2-220's 320′
    assert canonical_target('Sh2-296').extent_arcmin == 200  # not IC2177's 20′


@pytest.mark.parametrize('key', ['NGC3372', 'IC4628', 'M16', 'M17'])
def test_regions_without_sufficient_height_cannot_be_offered_from_buttes(tmp_path, monkeypatch, key):
    import astropilot.target_discovery as discovery_module
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    ref = datetime(2026, 6, 10, 18, tzinfo=timezone.utc)
    saved = profile()
    saved['location']['timezone'] = 'UTC'
    template = next(t for t in project_templates() if t['catalog_key'] == key)
    monkeypatch.setattr(discovery_module, 'project_templates', lambda: [template])
    client = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: weather_for(ref), clock=lambda: ref))
    response = client.post('/v1/target-suggestions', json=request())
    assert response.status_code == 200, response.text
    assert response.json()['suggestions'] == []
