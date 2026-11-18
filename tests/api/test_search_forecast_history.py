"""Synthetic snapshots only; no live forecast or running instance is accessed."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from fastapi.testclient import TestClient

from astropilot.app import create_app
from astropilot.search_forecast_history import FileSearchForecastHistory, SearchForecastHistoryError
from test_target_discovery import REF, profile, request
from test_clean_machine_all_night_regression import _weather_snapshot


def setup(tmp_path, monkeypatch, *, cloudy=False):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    saved = profile()
    saved['location']['name'] = 'Buttes FICTIF'
    weather = _weather_snapshot(reference_time=REF)
    payload = deepcopy(weather.payload)
    # Deliberately distinct exact provider values; never inferred from an observation.
    for key, value in [('cloud_cover', 100.0 if cloudy else 0.0),
                       ('cloud_cover_low', 3.25), ('cloud_cover_mid', 4.5), ('cloud_cover_high', 6.75)]:
        payload['hourly'][key] = [value] * weather.hour_count
    weather = replace(weather, payload=payload)
    calls = []
    def provider(*args):
        calls.append(args)
        return weather
    client = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=provider, clock=lambda: REF))
    return client, saved, weather, calls


@pytest.mark.parametrize('cloudy', [False, True])
def test_reopen_reads_exact_snapshot_without_weather_or_credit(tmp_path, monkeypatch, cloudy):
    client, saved, weather, calls = setup(tmp_path, monkeypatch, cloudy=cloudy)
    before = deepcopy(saved)
    reply = client.post('/v1/target-suggestions', json=request())
    assert reply.status_code == 200, reply.text
    assert reply.json()['status'] == ('no_suggestion' if cloudy else 'suggestions')
    key = reply.headers['X-NightMerit-Search-Id']
    raw_before = {p.name: p.read_bytes() for p in (tmp_path/'search_forecast_history').glob('*.json')}
    def forbidden(*args):
        raise AssertionError('Reading archives must never fetch weather')
    reopened = TestClient(create_app(profile_provider=lambda: saved, weather_provider=forbidden))
    listing = reopened.get('/v1/search-forecasts').json()
    assert listing['items'][0]['search_id'] == key
    assert listing['items'][0]['site'] == saved['location']
    response = reopened.get('/v1/search-forecasts/'+key)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    record = response.json()
    assert record['weather']['payload'] == weather.payload
    assert record['weather']['trust']['retrieved_at_utc'] == weather.retrieved_at_utc.isoformat()
    assert record['request']['site'] == saved['location']
    assert record['request']['parameters']['confirmed_filter_profile_ids'] == request()['confirmed_filter_profile_ids']
    assert raw_before == {p.name: p.read_bytes() for p in (tmp_path/'search_forecast_history').glob('*.json')}
    assert len(calls) == 1
    assert saved == before
    assert not (tmp_path/'user_profile.json').exists()
    assert {p.name for p in tmp_path.iterdir()} == {'search_forecast_history'}


def test_repeated_searches_have_distinct_records_and_paginate(tmp_path, monkeypatch):
    client, saved, weather, calls = setup(tmp_path, monkeypatch)
    ids = [client.post('/v1/target-suggestions', json=request()).headers['X-NightMerit-Search-Id'] for _ in range(2)]
    assert len(set(ids)) == 2
    first = client.get('/v1/search-forecasts?limit=1').json()
    second = client.get('/v1/search-forecasts?limit=1&before='+first['next_before']).json()
    assert {first['items'][0]['search_id'], second['items'][0]['search_id']} == set(ids)
    assert second['next_before'] is None
    assert len(calls) == 2


def test_empty_read_is_read_only_and_unknown_is_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path/'empty'))
    client = TestClient(create_app())
    assert client.get('/v1/search-forecasts').json() == {'items': [], 'next_before': None}
    assert client.get('/v1/search-forecasts/missing').status_code == 404
    assert client.get('/v1/search-forecasts?before=..').status_code == 422
    assert not (tmp_path/'empty').exists()


def test_no_successful_search_if_archival_fails(tmp_path, monkeypatch):
    client, saved, weather, calls = setup(tmp_path, monkeypatch)
    before = deepcopy(saved)
    def fail(*args, **kwargs):
        raise OSError('synthetic disk full')
    monkeypatch.setattr(FileSearchForecastHistory, 'save', fail)
    reply = client.post('/v1/target-suggestions', json=request())
    assert reply.status_code == 503
    assert reply.json()['detail']['code'] == 'search_forecast_history_unavailable'
    assert saved == before
    assert not list(tmp_path.rglob('*.json'))


def test_tonight_also_preserves_used_weather(tmp_path, monkeypatch):
    client, saved, weather, calls = setup(tmp_path, monkeypatch)
    from astro_score import build_durable_tonight_application_service
    client = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: weather, clock=lambda: REF,
        service_factory=build_durable_tonight_application_service))
    response = client.post('/v1/tonight', json={'availability': {'mode': 'all_night'}})
    # An empty portfolio can refuse, but its received weather remains traceable.
    rows = client.get('/v1/search-forecasts').json()['items']
    assert len(rows) == 1
    d = client.get('/v1/search-forecasts/'+rows[0]['search_id']).json()
    assert d['request']['kind'] == 'tonight'
    assert d['weather']['payload'] == weather.payload
    assert response.status_code == 200, response.text


def test_invalid_document_and_symlink_fail_closed(tmp_path, monkeypatch):
    client, saved, weather, calls = setup(tmp_path, monkeypatch)
    key = client.post('/v1/target-suggestions', json=request()).headers['X-NightMerit-Search-Id']
    path = tmp_path/'search_forecast_history'/f'{key}.json'
    d = json.loads(path.read_text()); d['weather']['payload']['hourly']['cloud_cover'][0] = 101
    path.write_text(json.dumps(d))
    assert client.get('/v1/search-forecasts/'+key).status_code == 503
    path.unlink(); path.symlink_to(tmp_path/'outside.json')
    assert client.get('/v1/search-forecasts/'+key).status_code == 503


def test_capacity_refuses_without_pruning(tmp_path, monkeypatch):
    client, saved, weather, calls = setup(tmp_path, monkeypatch)
    import astropilot.search_forecast_history as module
    monkeypatch.setattr(module, 'MAX_RECORDS', 1)
    assert client.post('/v1/target-suggestions', json=request()).status_code == 200
    before = {p.name:p.read_bytes() for p in (tmp_path/'search_forecast_history').glob('*.json')}
    assert client.post('/v1/target-suggestions', json=request()).status_code == 503
    assert before == {p.name:p.read_bytes() for p in (tmp_path/'search_forecast_history').glob('*.json')}


def test_backup_restore_preserves_search_forecast(tmp_path, monkeypatch):
    from astropilot.profile_backup import create_backup, inspect_backup, restore_empty
    from test_configuration_api import configuration_payload
    root = tmp_path/'original'; monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(root))
    weather = _weather_snapshot(reference_time=REF)
    client = TestClient(create_app(weather_provider=lambda *args: weather, clock=lambda:REF))
    assert client.put('/v1/configuration', json={**configuration_payload(projects={}), 'site': {'name': 'Buttes FICTIF', 'latitude':46.888, 'longitude':6.55, 'bortle':4}}).status_code == 200
    response = client.post('/v1/target-suggestions', json=request())
    assert response.status_code == 200, response.text
    key = response.headers['X-NightMerit-Search-Id']
    before = client.get('/v1/search-forecasts/'+key).json()
    archive, summary = create_backup(root)
    files, preview = inspect_backup(archive)
    dest = tmp_path/'restored'; restore_empty(dest, files)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(dest))
    reopened = TestClient(create_app(weather_provider=lambda *a: pytest.fail('unexpected weather fetch')))
    assert reopened.get('/v1/search-forecasts/'+key).json() == before
    assert reopened.get('/v1/configuration').json()['projects'] == {}
