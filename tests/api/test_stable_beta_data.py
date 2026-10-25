"""Synthetic stable beta roots only; never discover or touch operator profiles."""
import json
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest
from astropilot.app import create_app
from astropilot.profile_backup import BackupError, create_backup, inspect_backup, snapshot, validate_documents
from astropilot.stable_beta_data import MARKER, SCHEMA, prepare
from test_configuration_api import configuration_payload

A='a'*40
B='b'*40


@pytest.fixture
def stable(tmp_path, monkeypatch):
    profile=tmp_path/'private-beta'/'profil'
    prepare(profile,A)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(profile))
    client=TestClient(create_app())
    assert client.put('/v1/configuration',json=configuration_payload(projects={'M42':{'hours':0,'target_hours':15}})).status_code==200
    return profile


def quick_backup(root):
    return create_backup(root,validator=validate_documents)


def test_new_versions_resume_same_bytes_and_make_update_backup(stable):
    before=snapshot(stable)
    result=prepare(stable,B,backup_factory=quick_backup)
    assert result['backup_created'] is True
    assert snapshot(stable)==before
    backups=list((stable.parent/'SAUVEGARDES-AUTO').glob('*.zip'))
    assert len(backups)==1
    files,summary=inspect_backup(backups[0].read_bytes(),validator=validate_documents)
    assert files==before and summary['projects']==1
    assert json.loads((stable.parent/MARKER).read_bytes())=={'schema':SCHEMA,'last_build':B}
    assert prepare(stable,B,backup_factory=Mock(side_effect=AssertionError('no duplicate backup')))['backup_created'] is False
    assert list((stable.parent/'SAUVEGARDES-AUTO').glob('*.zip'))==backups


def test_real_graph_validation_before_update(stable):
    assert prepare(stable,B)['backup_created']
    assert list((stable.parent/'SAUVEGARDES-AUTO').glob('*.zip'))


def test_failed_update_backup_keeps_marker_and_profile_unchanged(stable):
    before=snapshot(stable);marker=(stable.parent/MARKER).read_bytes()
    with pytest.raises(OSError,match='disk full'):
        prepare(stable,B,backup_factory=Mock(side_effect=OSError('disk full')))
    assert snapshot(stable)==before and (stable.parent/MARKER).read_bytes()==marker


def test_existing_unregistered_data_is_never_silently_adopted(tmp_path):
    profile=tmp_path/'other'/'profil';profile.mkdir(parents=True)
    (profile/'user_profile.json').write_bytes(b'preserve')
    with pytest.raises(BackupError,match='explicit_adoption'):
        prepare(profile,A)
    assert (profile/'user_profile.json').read_bytes()==b'preserve'
    assert not (profile.parent/MARKER).exists()


@pytest.mark.parametrize('marker',[b'{bad',b'[]',b'{"schema":"future","last_build":"'+A.encode()+b'"}', b'x'*4097])
def test_incompatible_marker_blocks_before_profile_changes(stable,marker):
    path=stable.parent/MARKER;path.write_bytes(marker);before=snapshot(stable)
    with pytest.raises(BackupError):prepare(stable,B)
    assert path.read_bytes()==marker and snapshot(stable)==before


def test_empty_data_never_searches_or_imports_nearby_profiles(tmp_path):
    old=tmp_path/'old-kit'/'profil';old.mkdir(parents=True);(old/'user_profile.json').write_text('old')
    profile=tmp_path/'stable'/'profil'
    assert prepare(profile,A)['profile_state']=='empty'
    assert prepare(profile,B)['backup_created'] is False
    assert not profile.exists() and (old/'user_profile.json').read_text()=='old'


def test_linked_storage_and_unrecognized_root_are_rejected(tmp_path):
    outside=tmp_path/'original';outside.mkdir()
    link=tmp_path/'linked'
    try:link.symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('symlink privilege unavailable')
    with pytest.raises(BackupError):prepare(link/'profil',A)
    assert list(outside.iterdir())==[]
    root=tmp_path/'unknown';root.mkdir();(root/'notes.txt').write_text('keep')
    with pytest.raises(BackupError,match='unrecognized'):prepare(root/'profil',A)
    assert (root/'notes.txt').read_text()=='keep'


def test_read_failure_never_proceeds_to_update(stable):
    (stable/'user_profile.json').write_text('{broken')
    marker=(stable.parent/MARKER).read_bytes()
    with pytest.raises(BackupError):prepare(stable,B,backup_factory=quick_backup)
    assert (stable/'user_profile.json').read_text()=='{broken'
    assert (stable.parent/MARKER).read_bytes()==marker


def test_interrupted_metadata_publication_does_not_hide_the_stable_profile(stable):
    staging=stable.parent/'.publication';staging.mkdir(exist_ok=True)
    leftover=staging/'.stockage-beta.json.interrupted';leftover.write_text('unfinished metadata')
    before=snapshot(stable)
    assert prepare(stable,B,backup_factory=quick_backup)['backup_created']
    assert snapshot(stable)==before and leftover.read_text()=='unfinished metadata'


@pytest.mark.parametrize('name',['.publication','SAUVEGARDES-AUTO'])
def test_reserved_directories_cannot_be_replaced_by_files(stable,name):
    path=stable.parent/name
    if path.exists():path.rmdir()
    path.write_bytes(b'keep')
    before=snapshot(stable);marker=(stable.parent/MARKER).read_bytes()
    with pytest.raises(BackupError,match='invalid_directory'):prepare(stable,B)
    assert path.read_bytes()==b'keep' and snapshot(stable)==before
    assert (stable.parent/MARKER).read_bytes()==marker


def test_ambiguous_build_marker_is_rejected_without_advancing_it(stable):
    path=stable.parent/MARKER
    raw=('{"schema":"'+SCHEMA+'","last_build":"'+A+'","last_build":"'+B+'"}').encode()
    path.write_bytes(raw);before=snapshot(stable)
    with pytest.raises(BackupError,match='invalid_marker'):prepare(stable,B)
    assert path.read_bytes()==raw and snapshot(stable)==before
