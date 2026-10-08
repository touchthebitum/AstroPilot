"""Process-only supervision, including the 2026-10-08 missing-config trial."""
import os
import subprocess
import sys
from threading import Event

import pytest

from astropilot import opportunity_alert_windows_supervisor as supervisor


@pytest.mark.parametrize('codes,expected,launches,delays', [
    ([0], 0, 1, 0), ([2, 0], 0, 2, 1),
    ([2, 2, 2, 2], 2, 4, 3), ([-9, 0], 0, 2, 1),
    ([2, 0, 2], 0, 2, 1),
])
def test_bounded_restarts(codes, expected, launches, delays):
    seen, waits = [], []
    class Child:
        def wait(self, timeout):
            return codes[len(seen) - 1]
    def launch():
        seen.append(True)
        return Child()
    def wait(seconds):
        waits.append(seconds)
        return False
    assert supervisor.supervise(launch, Event(), restart_count=3,
                                restart_seconds=60, wait=wait) == expected
    assert len(seen) == launches
    assert waits == [60] * delays


def test_stop_parent_terminates_child(monkeypatch):
    stop = Event()
    class Child:
        def wait(self, timeout):
            stop.set()
            raise subprocess.TimeoutExpired('child', timeout)
    child = Child()
    stopped = []
    monkeypatch.setattr(supervisor, 'stop_child', stopped.append)
    assert supervisor.supervise(lambda: child, stop) == 0
    assert stopped == [child]


def test_stop_during_delay_never_restarts():
    launches = []
    class Child:
        def wait(self, timeout):
            return 2
    def launch():
        launches.append(True)
        return Child()
    assert supervisor.supervise(launch, Event(), wait=lambda _: True) == 0
    assert len(launches) == 1


def test_spawn_failure_is_bounded():
    launches = []
    def launch():
        launches.append(True)
        raise OSError('interpreter unavailable')
    assert supervisor.supervise(launch, Event(), wait=lambda _: False) == 2
    assert len(launches) == 4


def test_unexpected_parent_exception_cleans_child(monkeypatch):
    class Child:
        def wait(self, timeout):
            raise RuntimeError('unexpected parent failure')
    child = Child()
    stopped = []
    monkeypatch.setattr(supervisor, 'stop_child', stopped.append)
    with pytest.raises(RuntimeError):
        supervisor.supervise(lambda: child, Event())
    assert stopped == [child]


def test_launch_gates_host_until_contained(monkeypatch):
    calls = []
    class Input:
        def write(self, value):
            calls.append(('release', value))
        def close(self):
            calls.append('close')
    class Child:
        stdin = Input()
    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return Child()
    class Job:
        def assign(self, child):
            calls.append('assign')
    monkeypatch.setattr(supervisor.subprocess, 'Popen', popen)
    command = [sys.executable, '-u', '-m', supervisor.__name__, '--child',
               '--config', 'C:\\Espaces été\\config.json']
    supervisor.launch_child(command, Job())
    assert calls[1:] == ['assign', ('release', b'1'), 'close']
    assert calls[0][0] == command
    assert calls[0][1]['shell'] is False
    assert calls[0][1]['close_fds'] is True


def test_failed_containment_never_releases_host(monkeypatch):
    calls = []
    class Input:
        def close(self):
            calls.append('close')
        def write(self, value):
            pytest.fail('host released')
    class Child:
        stdin = Input()
    class Job:
        def assign(self, child):
            raise OSError('job assignment denied')
    monkeypatch.setattr(supervisor.subprocess, 'Popen', lambda *a, **k: Child())
    monkeypatch.setattr(supervisor, 'stop_child', lambda _: calls.append('stop'))
    with pytest.raises(OSError):
        supervisor.launch_child(['python'], Job())
    assert calls == ['close', 'stop']


@pytest.fixture
def deployment(tmp_path):
    root = tmp_path / 'Franck Testé 空间'
    root.mkdir()
    data, logs = root / 'data', root / 'logs'
    data.mkdir()
    logs.mkdir()
    config = root / 'config.json'
    config.write_text('{"schema_version":1,"interval_seconds":60,"policy":{},"availability":null}')
    return config, data, logs


def argv(deployment):
    config, data, logs = deployment
    return ['--python', sys.executable, '--config', str(config),
            '--data-dir', str(data), '--log-dir', str(logs)]


def test_duplicate_supervisor_never_launches(deployment, monkeypatch):
    from astropilot.opportunity_alert_host import host_lock
    monkeypatch.setattr(supervisor, 'launch_child', lambda *a: pytest.fail('child launched'))
    with host_lock(deployment[1] / '.opportunity_alert_windows_supervisor.lock'):
        assert supervisor.main(argv(deployment)) == 1


def test_missing_config_restored_before_retry(deployment, monkeypatch):
    # The XML logon action invokes main; the actual adapter child exits 2.
    # Restore during the injected 60-second wait; second real child succeeds.
    from astropilot.opportunity_alert_windows_task import build_task
    config, data, logs = deployment
    xml = build_task(python=sys.executable, config=config, data_dir=data,
                     log_dir=logs, user_id='S-1-5-21-123')
    assert supervisor.__name__ in xml
    original = config.read_bytes()
    config.unlink()
    returns = []
    real_launch = supervisor.launch_child
    def launch(command, job):
        # Isolated disabled host, one cycle: no notification or live network.
        command = list(command) + ['--once']
        child = real_launch(command, job)
        original_wait = child.wait
        def wait(timeout):
            result = original_wait(timeout=timeout)
            returns.append(result)
            return result
        child.wait = wait
        return child
    monkeypatch.setattr(supervisor, 'launch_child', launch)
    def wait(seconds):
        assert seconds == 60
        config.write_bytes(original)
        return False
    monkeypatch.setattr(supervisor, 'retry_wait', wait)
    assert supervisor.main(argv(deployment)) == 0
    assert returns == [2, 0]
    assert 'startup' in (logs / 'opportunity-alert-host.stdout.log').read_text()


def test_duplicate_host_stays_protected(deployment, monkeypatch):
    from astropilot.opportunity_alert_host import host_lock
    monkeypatch.setattr(supervisor, 'retry_wait', lambda _: False)
    with host_lock(deployment[1] / '.opportunity_alert_host.lock'):
        assert supervisor.main(argv(deployment)) != 0
    text = (deployment[2] / 'opportunity-alert-host.stdout.log').read_text()
    assert 'opportunity_alert_host_already_running' in text
    assert 'startup' not in text


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object native lifecycle')
def test_hard_parent_death_kills_contained_child(tmp_path):
    # A real parent owns a job; its child is inert, so no task is installed.
    marker = tmp_path / 'pid.txt'
    script = """
import subprocess, sys, time
from pathlib import Path
from astropilot.opportunity_alert_windows_job import WindowsJob
with WindowsJob() as job:
    child = subprocess.Popen([sys.executable, '-c', 'import sys,time; sys.stdin.buffer.read(1); time.sleep(120)'], stdin=subprocess.PIPE)
    job.assign(child)
    child.stdin.write(b'1'); child.stdin.close()
    Path(sys.argv[1]).write_text(str(child.pid))
    time.sleep(120)
"""
    parent = subprocess.Popen([sys.executable, '-c', script, str(marker)])
    import time
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = None
    try:
        deadline = time.monotonic() + 20
        while not marker.exists() and time.monotonic() < deadline:
            assert parent.poll() is None
            time.sleep(.05)
        assert marker.exists()
        handle = kernel.OpenProcess(0x00100000, False, int(marker.read_text()))
        assert handle
        parent.kill()
        parent.wait(timeout=10)
        assert kernel.WaitForSingleObject(handle, 10000) == 0
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)
        if handle:
            kernel.CloseHandle(handle)
