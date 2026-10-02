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


def test_regular_existing_key_loads(tmp_path):
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(bytes(range(32)))
    path.chmod(0o600)
    assert load_or_create_cursor_key(tmp_path) == bytes(range(32))


def test_symlink_key_is_rejected(tmp_path):
    external = tmp_path / 'external'
    external.write_bytes(b'x' * 32)
    external.chmod(0o600)
    path = tmp_path / '.outcome_history_cursor.key'
    try:
        path.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation unavailable')
    with pytest.raises(OutcomeHistoryCursorKeyError, match='type'):
        load_or_create_cursor_key(tmp_path)
    assert path.is_symlink()
    assert external.read_bytes() == b'x' * 32


def test_directory_key_is_rejected(tmp_path):
    (tmp_path / '.outcome_history_cursor.key').mkdir()
    with pytest.raises(OutcomeHistoryCursorKeyError, match='type'):
        load_or_create_cursor_key(tmp_path)


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='FIFO unavailable')
def test_fifo_key_is_rejected_without_blocking(tmp_path):
    import subprocess
    import sys
    os.mkfifo(tmp_path / '.outcome_history_cursor.key', 0o600)
    script = (
        'from pathlib import Path; import sys; '
        'from astropilot.outcome_history_cursor_key import load_or_create_cursor_key; '
        'load_or_create_cursor_key(Path(sys.argv[1]))'
    )
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            capture_output=True, timeout=5)
    assert result.returncode != 0
    assert b'invalid_outcome_history_cursor_key_type' in result.stderr


def test_oversized_key_read_is_bounded(tmp_path, monkeypatch):
    import astropilot.outcome_history_cursor_key as module
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(b'x' * (1024 * 1024))
    path.chmod(0o600)
    original = os.read
    reads = []
    def read(descriptor, size):
        chunk = original(descriptor, size)
        reads.append((size, len(chunk)))
        return chunk
    monkeypatch.setattr(module.os, 'read', read)
    with pytest.raises(OutcomeHistoryCursorKeyError, match='invalid'):
        load_or_create_cursor_key(tmp_path)
    assert reads == [(33, 33)]
    assert path.stat().st_size == 1024 * 1024


@pytest.mark.parametrize('nofollow', [True, False])
def test_symlink_swap_between_precheck_and_open_is_rejected(tmp_path, monkeypatch, nofollow):
    import astropilot.outcome_history_cursor_key as module
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(b'x' * 32)
    path.chmod(0o600)
    # Target the very same inode to exercise the post-open symlink check.
    external = tmp_path / 'external'
    os.link(path, external)
    probe = tmp_path / 'probe'
    try:
        probe.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip('symlink creation unavailable')
    probe.unlink()
    if not nofollow:
        monkeypatch.delattr(module.os, 'O_NOFOLLOW', raising=False)
    original = os.open
    def swapped_open(name, flags, *args, **kwargs):
        if Path(name) == path:
            path.unlink()
            path.symlink_to(external)
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(module.os, 'open', swapped_open)
    with pytest.raises(OutcomeHistoryCursorKeyError):
        load_or_create_cursor_key(tmp_path)
    assert path.is_symlink()
    assert external.read_bytes() == b'x' * 32


def test_replaced_regular_file_between_precheck_and_open_is_rejected(tmp_path, monkeypatch):
    import astropilot.outcome_history_cursor_key as module
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(b'x' * 32)
    path.chmod(0o600)
    replacement = tmp_path / 'replacement'
    replacement.write_bytes(b'y' * 32)
    replacement.chmod(0o600)
    original = os.open
    def swapped_open(name, flags, *args, **kwargs):
        if Path(name) == path:
            replacement.replace(path)
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(module.os, 'open', swapped_open)
    with pytest.raises(OutcomeHistoryCursorKeyError, match='changed'):
        load_or_create_cursor_key(tmp_path)


def test_bounded_read_handles_short_reads(tmp_path, monkeypatch):
    import astropilot.outcome_history_cursor_key as module
    path = tmp_path / '.outcome_history_cursor.key'
    path.write_bytes(b'x' * 32)
    path.chmod(0o600)
    original = os.read
    sizes = []
    def short_read(descriptor, size):
        sizes.append(size)
        return original(descriptor, min(size, 7))
    monkeypatch.setattr(module.os, 'read', short_read)
    assert load_or_create_cursor_key(tmp_path) == b'x' * 32
    assert sizes == [33, 26, 19, 12, 5, 1]


@pytest.mark.parametrize('content', [
    pytest.param(b'a' * 15 + b'\x1a' + b'b' * 16, id='ctrl-z'),
    pytest.param(b'a' * 15 + b'\r\n' + b'b' * 15, id='crlf'),
    pytest.param(b'a' * 14 + b'\x1a\r\n' + b'b' * 15, id='ctrl-z-and-crlf'),
])
def test_existing_key_preserves_binary_bytes(tmp_path, content):
    path = tmp_path / '.outcome_history_cursor.key'
    assert len(content) == 32
    path.write_bytes(content)
    path.chmod(0o600)
    assert load_or_create_cursor_key(tmp_path) == content


def test_key_open_includes_binary_flag(tmp_path, monkeypatch):
    import astropilot.outcome_history_cursor_key as module
    path = tmp_path / '.outcome_history_cursor.key'
    content = b'a' * 14 + b'\x1a\r\n' + b'b' * 15
    path.write_bytes(content)
    path.chmod(0o600)
    original = os.open
    native_binary = getattr(os, 'O_BINARY', 0)
    # Use a synthetic bit on POSIX; remove only that bit before the real open.
    binary = native_binary or (1 << 30)
    monkeypatch.setattr(module.os, 'O_BINARY', binary, raising=False)
    key_flags = []
    def binary_open(name, flags, *args, **kwargs):
        if Path(name) == path:
            key_flags.append(flags)
            assert flags & binary == binary
            assert flags & getattr(os, 'O_NOFOLLOW', 0) == getattr(os, 'O_NOFOLLOW', 0)
            assert flags & getattr(os, 'O_NONBLOCK', 0) == getattr(os, 'O_NONBLOCK', 0)
            if not native_binary:
                flags &= ~binary
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(module.os, 'open', binary_open)
    assert load_or_create_cursor_key(tmp_path) == content
    assert len(key_flags) == 1
