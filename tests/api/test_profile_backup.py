"""Synthetic stopped profiles only. No operator data or external weather."""
import io
import json
from pathlib import Path
import re
import zipfile

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.profile_backup import (BackupError, create_backup, inspect_backup,
                                      restore_empty, snapshot, validate_documents)
from astropilot.profile_transfer_app import create_transfer_app
from test_configuration_api import configuration_payload


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "old"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(root))
    response = TestClient(create_app()).put("/v1/configuration", json=configuration_payload(
        projects={"M42": {"hours": 0, "target_hours": 3}}))
    assert response.status_code == 200, response.text
    return root


def test_stopped_profile_roundtrip_preserves_bytes_and_original(source, tmp_path):
    before = snapshot(source)
    raw, summary = create_backup(source)
    assert summary == {"projects": 1, "sessions": 0, "observations": 0, "comparisons": 0}
    files, preview = inspect_backup(raw)
    assert files == before and preview["projects"] == 1
    target = tmp_path / "new"
    target.mkdir()  # Matches the empty folder created by the private launcher.
    assert restore_empty(target, files) == summary
    assert snapshot(target) == before == snapshot(source)
    # Read with the real API, with no fabricated session or credit.
    assert not (target / ".outcome_history_cursor.key").exists()
    with pytest.raises(BackupError, match="backup_destination_not_empty"):
        restore_empty(target, files)
    assert snapshot(target) == before


def test_runtime_state_is_not_a_portable_authority(source):
    (source / "Logs").mkdir()
    (source / "Logs/launcher.log").write_text("private runtime")
    (source / ".outcome_history_cursor.key").write_bytes(b"x" * 32)
    (source / "guardian").mkdir()
    (source / "guardian/lease").write_text("not portable")
    files = snapshot(source)
    assert set(files) == {"user_profile.json"}


@pytest.mark.parametrize("name", ["../user_profile.json", "/user_profile.json", "user_profile.json/extra",
                                  "field_observations/CON.json", "field_observations/../../outside.json"])
def test_archive_paths_rejected_before_writes(source, tmp_path, name):
    raw, _ = create_backup(source, validator=validate_documents)
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        manifest = json.loads(original.read("manifest.json"))
        profile = original.read("data/user_profile.json")
    manifest["files"][name] = manifest["files"].pop("user_profile.json")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("data/" + name, profile)
    with pytest.raises(BackupError):
        inspect_backup(buffer.getvalue(), validator=validate_documents)
    assert not (tmp_path / "outside.json").exists()


def test_corrupt_and_duplicate_zip_and_changed_snapshot_refused(source):
    raw, _ = create_backup(source, validator=validate_documents)
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        values = {name: original.read(name) for name in original.namelist()}
    for alteration in ["corrupt", "extra", "duplicate", "symlink"]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, value in values.items():
                archive.writestr(name, value + b" " if alteration == "corrupt" and name.startswith("data/") else value)
            if alteration == "extra": archive.writestr("executable.py", "no")
            if alteration == "duplicate":
                with pytest.warns(UserWarning): archive.writestr("manifest.json", values["manifest.json"])
            if alteration == "symlink":
                item = zipfile.ZipInfo("data/field_observations/link.json")
                item.external_attr = 0o120777 << 16
                archive.writestr(item, "outside")
        with pytest.raises(BackupError): inspect_backup(buffer.getvalue(), validator=validate_documents)
    def changing(files):
        (source / "user_filters.json").write_text("{}")
        return validate_documents(files)
    with pytest.raises(BackupError, match="backup_changed"):create_backup(source, validator=changing)


def test_unknown_files_and_symlinks_are_not_silently_dropped(source, tmp_path):
    unknown = source / "future-user-data.json"
    unknown.write_text("{}")
    with pytest.raises(BackupError, match="backup_unsupported_file"):snapshot(source)
    unknown.unlink()
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("keep")
    try: unknown.symlink_to(sentinel)
    except OSError: pytest.skip("Symlink creation unavailable")
    with pytest.raises(BackupError, match="backup_unsafe_path"):snapshot(source)
    assert sentinel.read_text() == "keep"


def test_private_preview_is_read_only_and_explicit_restore_is_create_only(source, tmp_path):
    raw, _ = create_backup(source, validator=validate_documents)
    destination = tmp_path / "fresh"
    app = create_transfer_app(destination, origin="http://testserver",
        inspector=lambda raw: inspect_backup(raw, validator=validate_documents),
        restorer=lambda root, files: restore_empty(root, files, validator=validate_documents))
    client = TestClient(app)
    html = client.get("/")
    token = re.search(r'const token="([^"]+)"', html.text)[1]
    headers = {"X-NightMerit-Transfer": token}
    assert client.get("/transfer/status").json()["can_restore"] is True
    assert not destination.exists()
    assert client.post("/transfer/preview", content=raw).status_code == 403
    assert client.post("/transfer/preview", content=raw, headers={**headers, "Origin": "https://outside.invalid"}).status_code == 403
    response = client.post("/transfer/preview", content=raw, headers=headers)
    assert response.status_code == 200 and not destination.exists()
    confirmation = response.json()["confirmation"]
    assert client.post("/transfer/restore", json={"confirmation":confirmation}, headers=headers).status_code == 409
    result = client.post("/transfer/restore", json={"confirmation":confirmation,"confirm":True}, headers=headers)
    assert result.status_code == 200
    assert snapshot(destination) == snapshot(source)
    assert client.post("/transfer/restore", json={"confirmation":confirmation,"confirm":True}, headers=headers).status_code == 409
    # The ordinary observing API is absent from this process.
    assert client.post("/v1/tonight", json={}, headers=headers).status_code == 404
    assert client.get("/", headers={"host":"attacker.invalid"}).status_code == 403


def test_destination_with_unknown_data_is_never_replaced(source, tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    (target / ".hidden").write_bytes(b"original")
    with pytest.raises(BackupError, match="backup_destination_not_empty"):
        restore_empty(target, snapshot(source), validator=validate_documents)
    assert (target / ".hidden").read_bytes() == b"original"


def test_invalid_preview_revokes_confirmation_and_occupied_target_stays_intact(source, tmp_path):
    raw, _ = create_backup(source, validator=validate_documents)
    target = tmp_path / 'target'
    client = TestClient(create_transfer_app(target, origin='http://testserver',
        inspector=lambda raw: inspect_backup(raw, validator=validate_documents),
        restorer=lambda root, files: restore_empty(root, files, validator=validate_documents)))
    token = re.search(r'const token="([^"]+)"', client.get('/').text)[1]
    headers = {'X-NightMerit-Transfer':token}
    nonce = client.post('/transfer/preview', content=raw, headers=headers).json()['confirmation']
    assert client.post('/transfer/preview', content=b'bad zip', headers=headers).status_code == 409
    assert client.post('/transfer/restore', json={'confirmation':nonce,'confirm':True}, headers=headers).status_code == 409
    nonce = client.post('/transfer/preview', content=raw, headers=headers).json()['confirmation']
    target.mkdir(); (target / 'sentinel').write_bytes(b'original')
    assert client.post('/transfer/restore', json={'confirmation':nonce,'confirm':True}, headers=headers).status_code == 409
    assert (target / 'sentinel').read_bytes() == b'original'


def test_failed_directory_publication_restores_empty_destination(source, tmp_path, monkeypatch):
    import astropilot.profile_backup as backup
    original = backup.os.rename
    target = tmp_path / 'target';target.mkdir()
    def fail_stage(src, dst):
        if Path(src).name == 'profile': raise OSError('synthetic disk failure')
        return original(src, dst)
    monkeypatch.setattr(backup.os, 'rename', fail_stage)
    with pytest.raises(OSError, match='synthetic'):
        restore_empty(target, snapshot(source), validator=validate_documents)
    assert target.is_dir() and not list(target.iterdir())
    assert not list(tmp_path.glob('.nightmerit-restore-*'))
    assert (source / 'user_profile.json').is_file()


def test_real_observations_roundtrip_does_not_create_sessions_or_comparisons(source, tmp_path):
    from test_saved_observation_catalogue import seed
    seed(source)
    before = snapshot(source)
    raw, summary = create_backup(source)
    assert summary['observations'] == 3 and summary['sessions'] == summary['comparisons'] == 0
    files, _ = inspect_backup(raw)
    target = tmp_path / 'new'
    restore_empty(target, files)
    assert snapshot(target) == before == snapshot(source)


def test_inconsistent_credit_is_refused_by_real_production_gate(tmp_path, monkeypatch):
    from test_execution_session_api import setup, create_completed, credit
    root = tmp_path / 'old'
    fresh = setup(root, monkeypatch)
    create_completed(fresh(), 'execution-1', evidence_id='evidence-1')
    assert credit(fresh(), 'execution-1', 'evidence-1', confirm=True).status_code == 200
    (root / 'execution_lineage/execution-1.json').unlink()
    before = snapshot(root)
    with pytest.raises(BackupError, match='backup_incompatible'):
        create_backup(root)
    assert snapshot(root) == before


def test_portable_modes_dispatch_before_normal_launcher(tmp_path):
    import subprocess, sys
    for flag, module, function, args in [
        ('--data-transfer', 'astropilot.profile_transfer_app', 'main', []),
        ('--validate-data-backup', 'astropilot.profile_backup', 'validate_profile_child', ['report'])]:
        script = f'''
import importlib.abc, sys, types
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('astropilot.launcher','astropilot.app'):
            raise AssertionError('ordinary application initialized')
sys.meta_path.insert(0, Block())
fake=types.ModuleType({module!r})
def called(*args): assert list(args)=={args!r}
setattr(fake,{function!r},called)
sys.modules[{module!r}]=fake
sys.argv=['AstroPilot',{flag!r}]+{args!r}
from astropilot.portable_entry import main
assert main()==0
'''
        subprocess.run([sys.executable, '-c', script], check=True, timeout=10)


def test_complete_session_and_observation_graph_roundtrip(tmp_path, monkeypatch):
    from test_tonight_api import (lineage_client, lineage_selection_payload,
        DEFAULT_WEATHER_REFERENCE_TIME, valid_profile, LINEAGE_START)
    import decision.services.durable_tonight_application_service as durable
    from astropilot.user_profile import save_user_profile
    from astro_score import build_durable_tonight_application_service
    from test_execution_session_api import create_completed, credit
    root = tmp_path / 'old'
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(root))
    monkeypatch.setattr(durable, 'generate_mission_id', lambda: 'mission-lineage')
    api = lineage_client(root, DEFAULT_WEATHER_REFERENCE_TIME)
    assert api.post('/v1/tonight', json={'availability':{'mode':'all_night'}}).status_code == 200
    accepted = api.post('/v1/decision-selections', json=lineage_selection_payload())
    assert accepted.status_code == 200, accepted.text
    profile = {**valid_profile(), 'projects': {'M31': {'hours':0, 'target_hours':4, 'imaging_field_id':'sh2-129_ou4',
        'acquisition_intent_progress':[{'acquisition_intent_id':'sh2-129_ha','acquired_duration_manual':0}],
        'acquisition_intent_targets':[{'acquisition_intent_id':'sh2-129_ha','target_hours':4}]}}}
    save_user_profile(profile)
    client = TestClient(create_app(service_factory=build_durable_tonight_application_service,
                                   guardian_renewal_enabled=False))
    create_completed(client, 'execution-1', mission_id='mission-lineage', evidence_id='evidence-1')
    from test_field_observation_api import payload
    recorded = client.post('/v1/field-observations', json=payload(
        observation_id='obs-1', decision_id='decision-lineage', execution_id=None,
        observed_at_utc=LINEAGE_START.isoformat(), recorded_at_utc=LINEAGE_START.isoformat()))
    assert recorded.status_code == 201, recorded.text
    compared = client.post('/v1/field-observations/obs-1/outcome-evaluation')
    assert compared.status_code == 201, compared.text
    applied = credit(client, 'execution-1', 'evidence-1', confirm=True)
    assert applied.status_code == 200, applied.text
    before = snapshot(root)
    raw, summary = create_backup(root)
    assert summary['sessions'] == summary['observations'] == summary['comparisons'] == 1
    files, _ = inspect_backup(raw)
    target = tmp_path / 'new'
    restore_empty(target, files)
    assert snapshot(target) == before == snapshot(root)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(target))
    resumed = TestClient(create_app(service_factory=build_durable_tonight_application_service,
                                   guardian_renewal_enabled=False))
    assert resumed.get('/v1/executions/execution-1/session').status_code == 200
    assert credit(resumed, 'execution-1', 'evidence-1').json()['status'] == 'already_applied'
    assert snapshot(target) == before


def test_preview_expiry_and_bounded_uploads(source, tmp_path, monkeypatch):
    import astropilot.profile_transfer_app as transfer
    raw, _ = create_backup(source, validator=validate_documents)
    client = TestClient(create_transfer_app(tmp_path / 'fresh', origin='http://testserver',
        inspector=lambda raw: inspect_backup(raw, validator=validate_documents)))
    token = re.search(r'const token="([^"]+)"', client.get('/').text)[1]
    headers = {'X-NightMerit-Transfer':token}
    nonce = client.post('/transfer/preview', content=raw, headers=headers).json()['confirmation']
    monotonic = transfer.time.monotonic
    monkeypatch.setattr(transfer.time, 'monotonic', lambda: monotonic() + 601)
    assert client.post('/transfer/restore', json={'confirmation':nonce,'confirm':True}, headers=headers).status_code == 409
    monkeypatch.setattr(transfer.time, 'monotonic', monotonic)
    monkeypatch.setattr(transfer, 'MAX_ARCHIVE', 10)
    assert client.post('/transfer/preview', content=b'x'*11, headers=headers).status_code == 409
    assert client.post('/transfer/restore', content=b'x'*4097, headers=headers).status_code == 409
    assert not (tmp_path / 'fresh').exists()


def test_duplicate_json_keys_and_future_versions_fail_before_restore(source):
    raw, _ = create_backup(source, validator=validate_documents)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        data = archive.read('data/user_profile.json')
    for kind in ['duplicate', 'future']:
        buffer = io.BytesIO()
        metadata = dict(manifest)
        metadata['application_version'] = '99.0.0' if kind == 'future' else metadata['application_version']
        encoded = json.dumps(metadata)
        if kind == 'duplicate': encoded = encoded[:-1] + ',"schema":"duplicate"}'
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('manifest.json', encoded)
            archive.writestr('data/user_profile.json', data)
        with pytest.raises(BackupError): inspect_backup(buffer.getvalue(), validator=validate_documents)


def test_writer_arriving_after_empty_check_cannot_be_deleted(source, tmp_path, monkeypatch):
    target = tmp_path / 'target';target.mkdir()
    rmdir = Path.rmdir
    def racing_rmdir(path):
        if path == target:
            (target / 'arrived.json').write_bytes(b'preserve late writer')
        return rmdir(path)
    monkeypatch.setattr(Path, 'rmdir', racing_rmdir)
    with pytest.raises(BackupError, match='backup_destination_not_empty'):
        restore_empty(target, snapshot(source), validator=validate_documents)
    assert (target / 'arrived.json').read_bytes() == b'preserve late writer'
