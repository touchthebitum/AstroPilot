import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astropilot.outcome_history_cursor_key import load_or_create_cursor_key, OutcomeHistoryCursorKeyError


def test_concurrent_initialization_and_restart(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: load_or_create_cursor_key(tmp_path / 'profile'), range(24)))
    assert len(set(keys)) == 1
    assert len(keys[0]) == 32
    path = tmp_path / 'profile' / '.outcome_history_cursor.key'
    assert path.read_bytes() == keys[0] == load_or_create_cursor_key(path.parent)
    assert not list(path.parent.glob('.outcome_history_cursor.key-*'))
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('content', [b'', b'x' * 31, b'x' * 33, b'00' * 32])
def test_corrupt_key_fails_without_rotation(tmp_path, content):
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(content)
    path.chmod(0o600)
    with pytest.raises(OutcomeHistoryCursorKeyError):
        load_or_create_cursor_key(tmp_path)
    assert path.read_bytes() == content


def test_production_and_direct_app_startup_share_stable_key(tmp_path, monkeypatch):
    import astro_score
    import astropilot.app as module
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    first = astro_score.build_durable_tonight_application_service()
    key = (tmp_path / '.outcome_history_cursor.key').read_bytes()
    assert first.outcome_history_service._cursor_key == key
    original = astro_score.build_durable_tonight_application_service
    built = []
    def factory():
        result = original()
        built.append(result)
        return result
    monkeypatch.setattr(astro_score, 'build_durable_tonight_application_service', factory)
    application = module.create_app()
    assert built == []
    with TestClient(application) as client:
        assert len(built) == 1
        assert built[0].outcome_history_service._cursor_key == key
        assert client.get('/v1/outcome-evaluations/history').status_code == 200
    assert (tmp_path / '.outcome_history_cursor.key').read_bytes() == key
    (tmp_path / '.outcome_history_cursor.key').unlink()
    with TestClient(application) as client:
        assert len(built) == 1
        assert client.get('/v1/outcome-evaluations/history').status_code == 200
    assert not (tmp_path / '.outcome_history_cursor.key').exists()


def test_direct_app_corrupt_key_fails_startup(tmp_path, monkeypatch):
    from astropilot.app import create_app
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(b'corrupt')
    with pytest.raises(OutcomeHistoryCursorKeyError):
        with TestClient(create_app()):
            pass
    assert path.read_bytes() == b'corrupt'


def test_concurrent_process_initialization(tmp_path):
    import subprocess
    import sys
    script = ('from pathlib import Path; from astropilot.outcome_history_cursor_key import load_or_create_cursor_key; '
              'load_or_create_cursor_key(Path(__import__("sys").argv[1]))')
    processes = [subprocess.Popen([sys.executable, '-c', script, str(tmp_path / 'profile')]) for _ in range(4)]
    assert [process.wait(timeout=20) for process in processes] == [0] * 4
    assert len(load_or_create_cursor_key(tmp_path / 'profile')) == 32


@pytest.mark.skipif(os.name == 'nt', reason='POSIX permissions')
def test_insecure_existing_key_permissions_fail(tmp_path):
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(b'x' * 32)
    path.chmod(0o644)
    with pytest.raises(OutcomeHistoryCursorKeyError, match='permissions'):
        load_or_create_cursor_key(tmp_path)
