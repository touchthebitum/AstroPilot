"""Payload exclusion gates without executing a binary or packaging anything."""
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def exporter(monkeypatch):
    # The workflow uses Python 3.13; allow these file-policy tests on 3.11 too.
    if not hasattr(Path, 'is_junction'):
        monkeypatch.setattr(Path, 'is_junction', lambda self: False, raising=False)
    spec = importlib.util.spec_from_file_location(
        'beta8_windows_artifacts', ROOT / 'scripts/prepare_beta8_windows_artifacts.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('relative', [
    '.env', '.env.production', 'user_profile.json', 'user_filters.json',
    '.user_profile.corrupt.example.json', 'opportunity_alert_ledger.json',
    'opportunity_alert_status.json', '.guardian_host.lock',
    'guardian_scheduler/state.json', 'decision_lineage/example.json',
    'field_observations/example.json', 'outcome_evaluations/example.json',
    'private.p12', 'private.pfx', 'private.key', 'private.pem',
    'other/cacert.pem', 'history.sqlite3', 'AstroPilot.log',
])
def test_payload_rejects_user_data_and_credentials(exporter, tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'synthetic')
    with pytest.raises(RuntimeError):
        exporter.scan_payload(tmp_path)


def test_payload_accepts_only_expected_certifi_pem(exporter, tmp_path):
    ca = tmp_path / '_internal/certifi/cacert.pem'
    ca.parent.mkdir(parents=True)
    ca.write_bytes(b'synthetic CA fixture')
    files, inventory = exporter.scan_payload(tmp_path)
    assert files == [ca]
    assert inventory[0]['path'] == '_internal/certifi/cacert.pem'


def test_payload_walk_read_error_is_not_ignored(exporter, tmp_path, monkeypatch):
    def failed_walk(path, *, followlinks, onerror):
        onerror(PermissionError('synthetic read error'))
        return iter(())
    monkeypatch.setattr(exporter.os, 'walk', failed_walk)
    with pytest.raises(PermissionError):
        exporter.scan_payload(tmp_path)


def test_workflow_checks_payload_before_installer():
    source = (ROOT / '.github/workflows/beta8-windows-manual.yml').read_text()
    assert source.index('--check-payload-only') < source.index('python scripts/build_windows_installer.py')
