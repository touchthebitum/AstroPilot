import dataclasses
import json
from pathlib import Path
import runpy

import pytest

from astropilot.field_lab_paths import field_lab_root, require_user_directory
from astropilot.field_lab_store import FieldLabArtifact, FileFieldLabStore
from astropilot.field_observation_store import FileFieldObservationStore
from astropilot.outcome_history_reader import FileOutcomeHistoryReader
from astropilot.recent_decision_reader import FileRecentDecisionReader
from decision.field_observation_persistence import deserialize_field_observation
from decision.storage_namespace import FIELD_LAB_PROVENANCE, require_user_document


@pytest.fixture
def roots(tmp_path, monkeypatch):
    user = tmp_path / 'user'
    lab = tmp_path / 'lab'
    user.mkdir()
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(user))
    monkeypatch.setenv('FIELD_LAB_DATA_DIR', str(lab))
    return user, lab


def artifact(**changes):
    values = dict(artifact_type='reference', source_id='station-1',
                  idempotency_key='sample-1', payload={'temperature_c': 7},
                  created_at_utc='2026-10-05T10:00:00+00:00')
    values.update(changes)
    return FieldLabArtifact.create(**values)


def test_roundtrip_immutable_idempotent_and_user_unchanged(roots):
    user, lab = roots
    (user / 'sentinel.json').write_text('{"user":true}')
    before = {str(p.relative_to(user)): p.read_bytes() for p in user.rglob('*') if p.is_file()}
    store = FileFieldLabStore()
    value = artifact()
    assert store.load(idempotency_key=value.idempotency_key) is None
    assert store.save(value) is True
    assert store.save(value) is False
    assert store.load(idempotency_key=value.idempotency_key) == value
    with pytest.raises(ValueError, match='immutable_conflict'):
        store.save(artifact(payload={'temperature_c': 8}))
    assert before == {str(p.relative_to(user)): p.read_bytes() for p in user.rglob('*') if p.is_file()}
    assert not list(lab.rglob('*.tmp'))


@pytest.mark.parametrize('mode', ['same', 'parent', 'child', 'symlink', 'traversal', 'relative'])
def test_overlap_and_traversal_rejected(roots, monkeypatch, mode):
    user, lab = roots
    choices = {'same': user, 'parent': user.parent, 'child': user / 'field_lab',
               'traversal': lab / '..' / 'lab', 'relative': Path('lab')}
    if mode == 'symlink':
        lab.symlink_to(user, target_is_directory=True)
        configured = lab
    else:
        configured = choices[mode]
    monkeypatch.setenv('FIELD_LAB_DATA_DIR', str(configured))
    with pytest.raises(ValueError):
        FileFieldLabStore()
    assert not list(user.iterdir())


def test_default_root_protected_and_missing_config(roots, monkeypatch):
    import astropilot.field_lab_paths as paths
    monkeypatch.setattr(paths, '_default_user_data_dir', lambda: roots[1])
    with pytest.raises(ValueError, match='overlap'):
        field_lab_root()
    monkeypatch.delenv('FIELD_LAB_DATA_DIR')
    with pytest.raises(ValueError, match='required'):
        FileFieldLabStore()


@pytest.mark.parametrize('field,value', [('calibration_eligible', True), ('calibration_eligible', 0),
                                       ('provenance', 'user'), ('namespace', 'user'),
                                       ('schema_version', True)])
def test_domain_cannot_be_changed(roots, field, value):
    with pytest.raises(ValueError):
        dataclasses.replace(artifact(), **{field: value})
    document = json.loads(artifact().document())
    document[field] = value
    with pytest.raises(ValueError):
        FieldLabArtifact.decode(json.dumps(document))
    assert artifact().calibration_eligible is False


def test_payload_copy_digest_and_utc(roots):
    payload = {'temperature_c': 7}
    value = artifact(payload=payload)
    payload['temperature_c'] = 99
    assert json.loads(value.payload_json)['temperature_c'] == 7
    document = json.loads(value.document())
    document['payload']['temperature_c'] = 99
    with pytest.raises(ValueError, match='digest'):
        FieldLabArtifact.decode(json.dumps(document))
    with pytest.raises(ValueError, match='utc'):
        artifact(created_at_utc='2026-10-05T10:00:00')


def test_user_stores_refuse_lab_even_without_env_and_through_alias(roots, monkeypatch):
    user, lab = roots
    FileFieldLabStore().save(artifact())
    alias = user.parent / 'alias'
    alias.symlink_to(lab, target_is_directory=True)
    for path in (lab, lab / 'artifacts', alias / 'artifacts'):
        with pytest.raises(ValueError):
            FileFieldObservationStore(path).load(observation_id='sample-1')
    monkeypatch.delenv('FIELD_LAB_DATA_DIR')
    for path in (lab, lab / 'artifacts', alias / 'artifacts'):
        with pytest.raises(ValueError):
            require_user_directory(path)


def test_symlink_subdirectory_and_final_file_rejected(roots):
    user, lab = roots
    store = FileFieldLabStore()
    store.save(artifact())
    for path in (lab / 'artifacts').iterdir():
        path.unlink()
    (lab / 'artifacts').rmdir()
    (lab / 'artifacts').symlink_to(user, target_is_directory=True)
    with pytest.raises(OSError):
        FileFieldLabStore().save(artifact())
    assert not list(user.iterdir())
    (lab / 'artifacts').unlink()
    store = FileFieldLabStore()
    store.save(artifact())
    final = next((lab / 'artifacts').glob('*.json'))
    final.unlink()
    target = user / 'sentinel'
    target.write_text('unchanged')
    final.symlink_to(target)
    with pytest.raises(OSError):
        store.load(idempotency_key='sample-1')
    with pytest.raises(OSError):
        store.save(artifact())
    assert target.read_text() == 'unchanged'


def test_configuration_redirection_after_construction(roots, monkeypatch):
    store = FileFieldLabStore()
    monkeypatch.setenv('FIELD_LAB_DATA_DIR', str(roots[0]))
    with pytest.raises(ValueError):
        store.save(artifact())
    assert not list(roots[0].iterdir())


@pytest.mark.parametrize('capability', ['platform', 'dir_fd', 'flags'])
def test_unsupported_capabilities_fail_before_writes(roots, monkeypatch, capability):
    import astropilot.field_lab_store as module
    if capability == 'platform':
        monkeypatch.setattr(module.os, 'name', 'nt')
    elif capability == 'dir_fd':
        monkeypatch.setattr(module.os, 'supports_dir_fd', set())
    else:
        monkeypatch.delattr(module.os, 'O_NOFOLLOW')
    with pytest.raises(RuntimeError, match='unavailable'):
        FileFieldLabStore()
    assert not roots[1].exists()


@pytest.mark.parametrize('key', ['../escape', '/absolute', 'a/b', '..'])
def test_identity_traversal(roots, key):
    with pytest.raises(ValueError):
        artifact(idempotency_key=key)
    with pytest.raises(ValueError):
        FileFieldLabStore().load(idempotency_key=key)
    assert not roots[1].exists()


def test_lab_envelope_in_user_history_and_recent_decisions_is_excluded(roots):
    user, lab = roots
    for kind in ('field_observations', 'outcome_evaluations', 'decision_forecast_evidence'):
        directory = user / kind
        directory.mkdir()
        (directory / 'sample-1.json').write_text(artifact().document())
    snapshot = FileOutcomeHistoryReader(user).read()
    assert not snapshot.observations and not snapshot.evaluations and not snapshot.evidence
    assert any(item['code'] == 'field_lab_document_excluded' for item in snapshot.diagnostics)
    result = FileRecentDecisionReader(user, cursor_key=b'x' * 32).list_recent(
        latitude=46.0, longitude=7.0, retrieved_from='2026-10-01T00:00:00Z',
        retrieved_to='2026-10-06T00:00:00Z')
    assert result['items'] == []
    assert result['diagnostics']
    with pytest.raises(ValueError, match='field_lab_document_excluded'):
        deserialize_field_observation(artifact().document(), observation_id='sample-1')


def test_valid_user_history_unchanged_and_tagged_user_shape_rejected(roots):
    user, lab = roots
    helpers = runpy.run_path(str(Path(__file__).parents[1] / 'history/test_outcome_history.py'))
    helpers['seed'](user)
    before = helpers['client'](user).get(helpers['URL']).json()
    FileFieldLabStore().save(artifact())
    after = helpers['client'](user).get(helpers['URL']).json()
    assert before == after
    assert before['statistics']['n_observations'] == 1
    observation = next((user / 'field_observations').glob('*.json'))
    document = json.loads(observation.read_text())
    document['observation']['provenance']['source_type'] = FIELD_LAB_PROVENANCE
    observation.write_text(json.dumps(document))
    snapshot = FileOutcomeHistoryReader(user).read()
    assert not snapshot.observations
    with pytest.raises(ValueError, match='excluded'):
        require_user_document(document)


def test_no_arbitrary_directory_argument(roots):
    with pytest.raises(TypeError):
        FileFieldLabStore(roots[0])


def test_marker_missing_corrupt_and_symlink_refused(roots):
    user, lab = roots
    lab.mkdir()
    with pytest.raises(ValueError, match='marker_missing'):
        FileFieldLabStore().load(idempotency_key='sample-1')
    store = FileFieldLabStore()
    store.save(artifact())
    marker = lab / '.field_lab_namespace'
    marker.write_text('user')
    with pytest.raises(ValueError):
        store.load(idempotency_key='sample-1')
    with pytest.raises(ValueError):
        store.save(artifact())
    marker.unlink()
    target = user / 'sentinel'
    target.write_text('unchanged')
    marker.symlink_to(target)
    with pytest.raises(OSError):
        store.save(artifact())
    assert target.read_text() == 'unchanged'


def test_duplicate_envelope_fields_refused(roots):
    document = artifact().document()
    document = document[:-1] + ',"calibration_eligible":true}'
    with pytest.raises(ValueError, match='duplicate'):
        FieldLabArtifact.decode(document)


def test_directory_swap_during_open_cannot_write_user(roots, monkeypatch):
    import astropilot.field_lab_store as module
    user, lab = roots
    FileFieldLabStore().save(artifact())
    for path in (lab / 'artifacts').iterdir():
        path.unlink()
    original = module.os.open
    swapped = False

    def swap(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == 'artifacts' and not swapped:
            swapped = True
            (lab / 'artifacts').rmdir()
            (lab / 'artifacts').symlink_to(user, target_is_directory=True)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, 'open', swap)
    with pytest.raises(OSError):
        FileFieldLabStore().save(artifact())
    assert swapped and not list(user.iterdir())


@pytest.mark.parametrize('module_name,function,kwargs', [
    ('decision.field_observation_persistence', 'deserialize_field_observation', {'observation_id': 'sample-1'}),
    ('decision.outcome_evaluation_persistence', 'deserialize_outcome_evaluation', {}),
    ('decision.weather.decision_forecast_evidence_persistence', 'deserialize_decision_forecast_evidence', {'decision_id': 'sample-1'}),
    ('decision.execution_record_persistence', 'deserialize_execution_record', {'execution_id': 'sample-1'}),
    ('decision.execution_lineage_persistence', 'deserialize_execution_lineage_aggregate', {}),
    ('decision.acceptance_lineage_persistence', 'deserialize_decision_acceptance_aggregate', {}),
])
def test_all_user_decoders_exclude_lab(module_name, function, kwargs):
    import importlib
    decoder = getattr(importlib.import_module(module_name), function)
    with pytest.raises(ValueError, match='field_lab_document_excluded'):
        decoder(artifact().document(), **kwargs)


def test_user_enumeration_cannot_create_lock_in_lab(roots):
    user, lab = roots
    FileFieldLabStore().save(artifact())
    before = {str(p.relative_to(lab)): p.read_bytes() for p in lab.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):
        FileFieldObservationStore(lab / 'artifacts').list_by_decision(decision_id='sample-1')
    assert before == {str(p.relative_to(lab)): p.read_bytes() for p in lab.rglob('*') if p.is_file()}


def test_unmarked_nonempty_root_cannot_be_claimed(roots):
    user, lab = roots
    lab.mkdir()
    sentinel = lab / 'user-profile.json'
    sentinel.write_text('{"user":true}')
    with pytest.raises(ValueError, match='unmarked_root_not_empty'):
        FileFieldLabStore().save(artifact())
    assert list(lab.iterdir()) == [sentinel]
    assert sentinel.read_text() == '{"user":true}'


def test_dangling_marker_still_excludes_user_stores(roots, monkeypatch):
    user, lab = roots
    lab.mkdir()
    (lab / '.field_lab_namespace').symlink_to(lab / 'missing')
    monkeypatch.delenv('FIELD_LAB_DATA_DIR')
    with pytest.raises(ValueError, match='excluded'):
        require_user_directory(lab)
