"""Process-only supervision, without installing OS startup jobs."""
import os
import subprocess
import sys
from threading import Event

import pytest

from astropilot import guardian_os_supervisor as supervisor


@pytest.mark.parametrize('codes,expected,launches,delays', [
    ([0], 0, 1, 0), ([2, 0], 0, 2, 1),
    ([2, 2, 2], 2, 3, 2), ([-9, 0], 0, 2, 1),
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
    assert len(launches) == 3


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


def test_gate_eof_exits_before_host_import():
    result = subprocess.run([sys.executable, '-u', '-m', supervisor.__name__, '--child'],
                            input=b'', capture_output=True, timeout=20)
    assert result.returncode == 2
    assert result.stdout == b''
    assert result.stderr == b''


def test_stop_child_escalates_and_reaps():
    calls = []
    class Child:
        def poll(self):
            return None
        def send_signal(self, signum):
            calls.append(('signal', signum))
        def wait(self, timeout):
            calls.append(('wait', timeout))
            if len(calls) == 2:
                raise subprocess.TimeoutExpired('child', timeout)
        def kill(self):
            calls.append('kill')
    supervisor.stop_child(Child())
    assert calls[1:] == [('wait', 10), 'kill', ('wait', 10)]


@pytest.fixture
def deployment(tmp_path):
    root = tmp_path / 'Franck Testé 空间'
    root.mkdir()
    data, logs = root / 'data', root / 'logs'
    data.mkdir()
    logs.mkdir()
    config = root / 'config.json'
    config.write_text('{"schema_version":1,"interval_seconds":60,"anchor":"2026-01-01T00:00:00+00:00"}')
    return config, data, logs


def argv(deployment):
    config, data, logs = deployment
    return ['--python', sys.executable, '--config', str(config),
            '--data-dir', str(data), '--log-dir', str(logs)]


def test_duplicate_supervisor_never_launches(deployment, monkeypatch):
    from astropilot.guardian_host import host_lock
    monkeypatch.setattr(supervisor, 'launch_child', lambda *a: pytest.fail('child launched'))
    with host_lock(deployment[1] / '.guardian_os_supervisor.lock'):
        assert supervisor.main(argv(deployment)) == 1


def test_invalid_config_fails_fast(deployment, monkeypatch):
    deployment[0].write_text('{}')
    monkeypatch.setattr(supervisor, 'launch_child', lambda *a: pytest.fail('child launched'))
    assert supervisor.main(argv(deployment)) == 2


def test_duplicate_host_stays_protected(deployment, monkeypatch):
    from astropilot.guardian_host import host_lock
    import json
    config, data, logs = deployment
    config.write_text(json.dumps({'schema_version':1, 'interval_seconds':60,
        'anchor':'2026-01-01T00:00:00+00:00', 'enabled':True, 'provider':'test'}))
    monkeypatch.setattr(supervisor, 'retry_wait', lambda _: False)
    with host_lock(data / '.guardian_host.lock'):
        assert supervisor.main(argv(deployment)) != 0
    assert 'host_already_running' in (logs / 'guardian-host.stdout.log').read_text()
    assert '"event": "cycle"' not in (logs / 'guardian-host.stdout.log').read_text()


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


def test_config_becomes_invalid_during_wait_fails_fast(deployment, monkeypatch):
    launches = []
    class Child:
        def wait(self, timeout):
            return 7
    monkeypatch.setattr(supervisor, 'launch_child', lambda *a: launches.append(True) or Child())
    def wait(seconds):
        deployment[0].write_text('{}')
        return False
    monkeypatch.setattr(supervisor, 'retry_wait', wait)
    assert supervisor.main(argv(deployment)) == 2
    assert len(launches) == 1
    diagnostic = (deployment[2] / 'guardian-host.stderr.log').read_text()
    assert diagnostic == 'guardian_supervisor_child_exit=7 attempt=0\n'


def test_append_logs_and_no_cwd_dependency(deployment, tmp_path):
    from pathlib import Path
    env = os.environ | {'PYTHONPATH': str(Path(__file__).resolve().parents[2])}
    command = [sys.executable, '-m', supervisor.__name__, *argv(deployment)]
    for _ in range(2):
        result = subprocess.run(command, cwd=tmp_path, env=env,
                                capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
    text = (deployment[2] / 'guardian-host.stdout.log').read_text()
    assert text.count('"event": "startup"') == 2
    assert text.count('"event": "shutdown"') == 2
    assert (deployment[2] / 'guardian-host.stderr.log').read_text() == ''


@pytest.mark.skipif(os.name == 'nt', reason='POSIX cooperative signal lifecycle')
def test_real_parent_sigterm_reaps_child(deployment, tmp_path):
    import time
    import signal
    marker = tmp_path / 'child.pid'
    script = """
import sys
from pathlib import Path
from astropilot import guardian_os_supervisor as s
real_launch = s.launch_child
def launch(command, job):
    child = real_launch([sys.executable, '-c', 'import sys,time; sys.stdin.buffer.read(1); time.sleep(120)'], job)
    Path(sys.argv[1]).write_text(str(child.pid))
    return child
s.launch_child = launch
sys.exit(s.main(sys.argv[2:]))
"""
    parent = subprocess.Popen([sys.executable, '-c', script, str(marker), *argv(deployment)])
    child_pid = None
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            assert parent.poll() is None
            time.sleep(.02)
        assert marker.exists()
        child_pid = int(marker.read_text())
        parent.send_signal(signal.SIGTERM)
        assert parent.wait(timeout=15) == 0
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if parent.poll() is None:
            parent.send_signal(signal.SIGTERM)
            parent.wait(timeout=15)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_layer_boundary():
    import ast
    import inspect
    from astropilot import guardian_launchd, guardian_windows_task, guardian_task_host
    for module in (supervisor, guardian_launchd, guardian_windows_task, guardian_task_host):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any(name and name.startswith('decision') for name in imports)
        assert 'GuardianService' not in source and 'GuardianRunner' not in source
        assert 'shell=True' not in source
        assert not any(name and any(x in name for x in ('notification', 'field_lab', 'reference_station')) for name in imports)
        alert_imports = {name for name in imports if name and 'opportunity_alert' in name}
        assert alert_imports <= {'astropilot.opportunity_alert_windows_job'}
