"""Profile-local saved report discovery; reads never create observations or comparisons."""
from dataclasses import replace
from datetime import timedelta
import runpy
from pathlib import Path

import pytest

from astropilot.field_observation_store import FileFieldObservationStore
from decision.field_observation_persistence import FieldObservationPersistenceError

ROOT = Path(__file__).resolve().parents[2]
BUILDERS = runpy.run_path(str(ROOT / 'tests/architecture/test_field_observation_persistence_contract.py'))
API = runpy.run_path(str(Path(__file__).with_name('test_field_observation_api.py')))


def seed(tmp_path):
    store = FileFieldObservationStore(tmp_path / 'field_observations')
    base = BUILDERS['observation']()
    for i in range(3):
        store.save(observation=replace(base, observation_id=f'obs-{i}',
            observed_at_utc=base.observed_at_utc - timedelta(days=i)))
    return store


def test_profile_local_pages_newest_first_and_no_record_writes(tmp_path):
    store = seed(tmp_path)
    files = {p.name: p.read_bytes() for p in (tmp_path / 'field_observations').glob('*.json')}
    first = store.list_page(limit=2)
    assert [o.observation_id for o in first['items']] == ['obs-0', 'obs-1']
    second = store.list_page(limit=2, before=first['next_before'])
    assert [o.observation_id for o in second['items']] == ['obs-2']
    assert second['next_before'] is None
    assert files == {p.name: p.read_bytes() for p in (tmp_path / 'field_observations').glob('*.json')}
    other = FileFieldObservationStore(tmp_path / 'another-profile' / 'field_observations')
    assert other.list_page() == {'items': [], 'next_before': None}
    for limit in [0, 51, True]:
        with pytest.raises(ValueError):
            store.list_page(limit=limit)
    with pytest.raises(ValueError):
        store.list_page(before='missing')


def test_catalogue_refuses_corruption_oversize_and_symlinks(tmp_path):
    store = seed(tmp_path)
    bad = tmp_path / 'field_observations' / 'bad.json'
    bad.write_text('{broken')
    with pytest.raises((ValueError, FieldObservationPersistenceError)):
        store.list_page(limit=1)  # even a corrupt older report must not be silently omitted
    bad.write_bytes(b'x' * (1024 * 1024 + 1))
    with pytest.raises(FieldObservationPersistenceError, match='scan_limit'):
        store.list_page()
    bad.unlink()
    external = tmp_path / 'external.json'
    external.write_text('private sentinel')
    try:
        bad.symlink_to(external)
    except OSError:
        pytest.skip('Host cannot create test symlinks')
    with pytest.raises(FieldObservationPersistenceError, match='unsafe_file'):
        store.list_page()
    assert external.read_text() == 'private sentinel'


def test_catalogue_refuses_file_replacement_before_read(tmp_path):
    store = seed(tmp_path)
    path = tmp_path / 'field_observations' / 'obs-0.json'
    before = path.lstat()
    old = path.with_suffix('.old')
    path.rename(old)
    path.write_bytes(old.read_bytes())
    with pytest.raises(FieldObservationPersistenceError, match='unsafe_file'):
        store._load_catalogue_path(path, before)


def client_for_store(store):
    service = API['FieldObservationService']()
    service.list_saved_field_observations = store.list_page
    service.resolve_saved_field_observation_context = service.context
    client = API['TestClient'](API['create_app'](service_factory=lambda: service, clock=lambda: API['NOW']))
    return client, service


def test_saved_observations_api_pagination_and_confirmed_timezone(tmp_path):
    store = seed(tmp_path)
    client, service = client_for_store(store)
    first = client.get('/v1/field-observations?limit=2')
    assert first.status_code == 200
    result = first.json()
    assert [o['observation']['observation_id'] for o in result['items']] == ['obs-0', 'obs-1']
    assert result['items'][0]['context']['timezone'] == 'Europe/Zurich'
    assert result['items'][0]['context']['site_name'] == 'Buttes'
    second = client.get('/v1/field-observations', params={'before': result['next_before']})
    assert second.json()['items'][0]['observation']['observation_id'] == 'obs-2'
    assert service.observations == {}  # GET never records through the application writer
    for params in [{'limit': 0}, {'limit': 51}, {'before': '../outside'}, {'before': 'missing'}]:
        assert client.get('/v1/field-observations', params=params).status_code == 422


def test_missing_lineage_is_not_an_empty_library_or_guessed_timezone(tmp_path):
    from decision.services.field_observation_context import FieldObservationContextError
    store = seed(tmp_path)
    client, service = client_for_store(store)
    def unavailable(_observation):
        raise FieldObservationContextError('decision_not_found')
    service.resolve_saved_field_observation_context = unavailable
    data = client.get('/v1/field-observations').json()
    assert len(data['items']) == 3
    assert all(item['context'] is None for item in data['items'])
    (tmp_path / 'field_observations' / 'broken.json').write_text('{}')
    assert client.get('/v1/field-observations').status_code == 500


def test_production_composition_lists_saved_records_after_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    seed(tmp_path)
    with API['TestClient'](API['create_app'](guardian_renewal_enabled=False)) as client:
        result = client.get('/v1/field-observations')
        assert result.status_code == 200
        assert len(result.json()['items']) == 3
        assert all(item['context'] is None for item in result.json()['items'])
