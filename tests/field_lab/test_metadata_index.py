import hashlib
import json
import os
from pathlib import Path

import pytest

from astropilot.field_lab_store import FieldLabArtifact, FileFieldLabStore
from astropilot.field_lab_collection import usage, check_capacity
from astropilot.reference_station_lab import ReferenceLab

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Secure storage requires POSIX')
STAMP = '2026-10-09T00:00:00+00:00'


@pytest.fixture
def indexed(tmp_path, monkeypatch):
    monkeypatch.setenv('FIELD_LAB_DATA_DIR', str(tmp_path/'lab'))
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path/'user'))
    store = FileFieldLabStore()
    for i in range(4):
        store.save(fact(str(i)))
    return store, tmp_path/'lab'


def fact(key):
    return FieldLabArtifact.create(artifact_type='index_test', source_id='test',
        idempotency_key=key, payload={'value':key}, created_at_utc=STAMP)


def originals(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ('artifacts', 'metadata') for p in (root/directory).iterdir()}


def test_generation_parity_sequential_reads_and_refresh_retention(indexed, monkeypatch):
    store, root = indexed
    expected = sorted(store.iter_metadata(), key=lambda m:m['idempotency_key'])
    before = originals(root)
    result = store.rebuild_metadata_index(workers=2)
    assert result['indexed_count'] == 4
    read = store._read
    def no_sidecars(fd, name):
        if name.endswith('.json') and not name.endswith('.commit.json'):
            pytest.fail('indexed scan reopened an individual sidecar')
        return read(fd, name)
    monkeypatch.setattr(store, '_read', no_sidecars)
    assert sorted(store.iter_metadata(), key=lambda m:m['idempotency_key']) == expected
    monkeypatch.setattr(store, '_read', read)
    store.save(fact('new'))
    assert len(list(store.iter_metadata())) == 5
    first_generation = set((root/'metadata-index').iterdir())
    store.rebuild_metadata_index()
    assert first_generation <= set((root/'metadata-index').iterdir())
    assert len(list(store.iter_metadata())) == 5
    assert all(originals(root)[name] == value for name, value in before.items())


def test_interrupted_publication_still_visible_and_idempotent(indexed, monkeypatch):
    store, root = indexed
    store.rebuild_metadata_index()
    save_metadata = store._save_metadata
    def crash(artifact):
        raise OSError('interrupted before sidecar')
    monkeypatch.setattr(store, '_save_metadata', crash)
    with pytest.raises(OSError):
        store.save(fact('interrupted'))
    assert len(list(store.iter_metadata())) == 5
    monkeypatch.setattr(store, '_save_metadata', save_metadata)
    assert store.save(fact('interrupted')) is False
    with store.writer_lock() as state:
        assert state['count'] == 5


@pytest.mark.parametrize('suffix', ['.names', '.rows', '.offsets', '.commit.json'])
def test_corrupt_generation_fails_closed_and_force_rebuild_recovers(indexed, suffix):
    store, root = indexed
    generation = store.rebuild_metadata_index()['generation']
    before = originals(root)
    target = root/'metadata-index'/(generation+suffix)
    data = target.read_bytes()
    target.write_bytes(data[:-1]+bytes([data[-1]^1]))
    with pytest.raises((ValueError, KeyError)):
        next(store.iter_metadata())
    store.rebuild_metadata_index(force=True)
    assert len(list(store.iter_metadata())) == 4
    assert originals(root) == before
    assert target.exists()  # Corrupt derived generation is retained too.


def test_missing_index_and_interrupted_build_use_legacy_path(indexed, monkeypatch):
    store, root = indexed
    publish = store._publish
    def interrupted(fd, name, document, **kwargs):
        if name.endswith('.commit.json'):
            raise OSError('before index commit')
        return publish(fd, name, document, **kwargs)
    monkeypatch.setattr(store, '_publish', interrupted)
    with pytest.raises(OSError):
        store.rebuild_metadata_index()
    assert len(list(store.iter_metadata())) == 4
    monkeypatch.setattr(store, '_publish', publish)
    store.rebuild_metadata_index()
    assert len(list(store.iter_metadata())) == 4


def test_limit_checked_before_index_rows_or_payloads(indexed, monkeypatch):
    store, root = indexed
    store.rebuild_metadata_index()
    store.save(fact('tail'))
    def forbidden(*args, **kwargs):
        pytest.fail('payload read before name limit')
    monkeypatch.setattr(store, '_legacy_metadata', forbidden)
    with pytest.raises(ValueError, match='name_limit_exceeded'):
        next(store.iter_metadata(max_names=4))
    with pytest.raises(ValueError, match='name_limit_exceeded'):
        next(store.iter_metadata(max_names=3))


@pytest.mark.parametrize('location', ['artifacts', 'metadata', 'metadata-index'])
def test_index_does_not_bypass_nofollow_checks(indexed, location, tmp_path):
    store, root = indexed
    store.rebuild_metadata_index()
    target = next((root/location).iterdir())
    target.unlink()
    target.symlink_to(tmp_path/'outside')
    with pytest.raises((OSError, ValueError)):
        next(store.iter_metadata())


def test_removed_authoritative_fact_fails_closed(indexed):
    store, root = indexed
    store.rebuild_metadata_index()
    next((root/'artifacts').iterdir()).unlink()
    with pytest.raises(ValueError, match='missing_authoritative_fact'):
        next(store.iter_metadata())


def test_filtered_load_still_validates_authoritative_digest(indexed):
    store, root = indexed
    store.rebuild_metadata_index()
    path = root/'artifacts'/store._name('0')
    value = json.loads(path.read_text())
    value['payload']['value'] = 'corrupt'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='digest_mismatch'):
        list(store.iter_artifacts())


def test_maintenance_uses_same_lock_and_never_nests(indexed):
    store, root = indexed
    with store.writer_lock():
        with pytest.raises(RuntimeError, match='writer_busy'):
            store.rebuild_metadata_index()
    with store.maintenance_lock():
        import subprocess, sys
        child = subprocess.run([sys.executable, '-c',
            'from astropilot.field_lab_store import FileFieldLabStore, FieldLabArtifact; '
            'FileFieldLabStore().save(FieldLabArtifact.create(artifact_type="test", '
            'source_id="test", idempotency_key="concurrent", payload={}, '
            f'created_at_utc="{STAMP}"))'], capture_output=True, text=True)
        assert child.returncode != 0 and 'writer_busy' in child.stderr


def test_capacity_retains_ceiling_with_index_and_new_tail(indexed):
    store, root = indexed
    store.rebuild_metadata_index()
    lab = ReferenceLab(max_artifacts=10)
    with lab.store.writer_lock(max_names=10):
        for i in range(4):
            lab.store.save(fact('tail-'+str(i)))
        assert usage(lab)['count'] == 8
        with pytest.raises(ValueError, match='capacity_stop'):
            check_capacity(lab)
        with pytest.raises(ValueError, match='capacity_stop'):
            lab.store.save(fact('refused'))
    assert lab.store.load(idempotency_key='refused') is None


def test_disk_scan_is_explicit_and_not_part_of_admission(indexed, monkeypatch):
    store, root = indexed
    store.rebuild_metadata_index()
    lab = ReferenceLab()
    assert usage(lab)['disk_bytes'] is None
    assert usage(lab, include_disk=True)['disk_bytes'] > 0
    assert check_capacity(lab)['disk_usage_measured'] is False


def test_locked_capacity_reuses_exact_count_and_recounts_next_writer(indexed, monkeypatch):
    store, root = indexed
    store.rebuild_metadata_index()
    read = store.iter_metadata
    with store.writer_lock() as state:
        monkeypatch.setattr(store, 'iter_metadata', lambda **kw:pytest.fail('redundant locked recount'))
        assert store.capacity_count() == 4
        store.save(fact('locked-new'))
        assert store.capacity_count() == 5
        with pytest.raises(ValueError, match='name_limit_exceeded'):
            store.capacity_count(max_names=4)
    monkeypatch.setattr(store, 'iter_metadata', read)
    with store.writer_lock() as state:
        assert state['count'] == 5


def test_refresh_is_opt_in_and_retains_old_generations(indexed):
    store, root = indexed
    assert store.refresh_metadata_index(count=4, threshold=1) is None
    assert not (root/'metadata-index').exists()
    store.rebuild_metadata_index()
    first = set((root/'metadata-index').iterdir())
    store.save(fact('new'))
    assert store.refresh_metadata_index(count=5, threshold=2) is None
    assert store.refresh_metadata_index(count=5, threshold=1)['indexed_count'] == 5
    assert first <= set((root/'metadata-index').iterdir())


def test_status_only_scans_metadata_once(indexed, monkeypatch):
    import astropilot.field_lab_collection as collection
    store, root = indexed
    store.rebuild_metadata_index()
    lab = ReferenceLab()
    original = lab.store.iter_metadata
    calls = []
    def counted(**kwargs):
        calls.append(1)
        yield from original(**kwargs)
    monkeypatch.setattr(lab.store, 'iter_metadata', counted)
    monkeypatch.setattr(collection, 'scheduler', lambda *args, **kw:{})
    assert collection.status(lab)['usage']['count'] == 4
    assert len(calls) == 1
