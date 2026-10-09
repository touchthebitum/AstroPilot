import subprocess
import sys
import time
from pathlib import Path

import pytest

from astropilot import guardian_http_transport as transport
from astropilot import guardian_http_worker as worker


class Socket:
    def settimeout(self, value):
        assert 0 < value <= 2


def connection_factory(body=b'{}', status=200, failure=None):
    calls = []
    class Connection:
        sock = Socket()
        def __init__(self, host, timeout):
            assert host == 'api.open-meteo.com'
            assert 0 < timeout <= 2
        def request(self, method, path):
            calls.append((method, path))
            if failure == 'connect':
                raise TimeoutError('secret')
        def getresponse(self):
            if failure == 'headers':
                raise TimeoutError('secret')
            class Response:
                def __init__(self):
                    self.status = status
                    self.remaining = body
                def read1(self, size):
                    if failure == 'read':
                        raise TimeoutError('secret')
                    chunk, self.remaining = self.remaining[:size], self.remaining[size:]
                    return chunk
            return Response()
        def close(self):
            calls.append('close')
    return Connection, calls


@pytest.mark.parametrize('platform', ['darwin', 'linux', 'win32'])
def test_portable_success_and_fixed_command(monkeypatch, platform):
    monkeypatch.setattr(sys, 'platform', platform)
    calls = []
    def run(command, **options):
        calls.append(command)
        assert command[0] == sys.executable
        assert command[1] == '-I'
        assert Path(command[2]).is_absolute()
        assert options['timeout'] <= 2
        assert options['stderr'] == subprocess.DEVNULL
        assert 'shell' not in options
        return subprocess.CompletedProcess(command, 0, b'{}')
    monkeypatch.setattr(transport.subprocess, 'run', run)
    assert transport.BoundedHttpTransport()(latitude=46, longitude=7, timeout_seconds=2) == {}
    assert len(calls) == 1


def test_proxy_ignored_and_one_request(monkeypatch):
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'https_proxy'):
        monkeypatch.setenv(name, 'http://secret.invalid:9999')
    factory, calls = connection_factory()
    monkeypatch.setattr(worker, 'HTTPSConnection', factory)
    assert worker.request(46, 7, 2) == b'{}'
    assert len(calls) == 2
    assert calls[0][0] == 'GET'
    assert calls[0][1].startswith('/v1/forecast?')
    assert 'current=rain%2Cshowers' in calls[0][1]
    assert calls[1] == 'close'


@pytest.mark.parametrize('status', [301, 302, 307, 308, 500])
def test_redirect_and_non_200_rejected(monkeypatch, status):
    factory, calls = connection_factory(status=status)
    monkeypatch.setattr(worker, 'HTTPSConnection', factory)
    with pytest.raises(ValueError): worker.request(46, 7, 2)
    assert len(calls) == 2


@pytest.mark.parametrize('failure', ['connect', 'headers', 'read'])
def test_phase_timeout_closes_without_retry(monkeypatch, failure):
    factory, calls = connection_factory(failure=failure)
    monkeypatch.setattr(worker, 'HTTPSConnection', factory)
    with pytest.raises(TimeoutError): worker.request(46, 7, 2)
    assert len(calls) == 2
    assert calls[-1] == 'close'


@pytest.mark.parametrize('size,ok', [(65536, True), (65537, False)])
def test_body_cap(monkeypatch, size, ok):
    factory, calls = connection_factory(body=b'x' * size)
    monkeypatch.setattr(worker, 'HTTPSConnection', factory)
    if ok: assert len(worker.request(46, 7, 2)) == size
    else:
        with pytest.raises(ValueError): worker.request(46, 7, 2)
    assert calls[-1] == 'close'


@pytest.mark.parametrize('body', [b'{', b'{"x": NaN}', b'{"x": Infinity}', b'x'*65537],
                         ids=['malformed', 'nan', 'infinity', 'oversize'])
def test_bad_child_output_fails_closed(monkeypatch, body):
    monkeypatch.setattr(transport.subprocess, 'run', lambda *a, **k:
        subprocess.CompletedProcess(a, 0, body))
    with pytest.raises(transport.TransportError, match='acquisition_failed'):
        transport.BoundedHttpTransport()(latitude=46, longitude=7, timeout_seconds=2)


def test_native_parent_timeout_kills_and_reaps(tmp_path, monkeypatch):
    helper = tmp_path / 'blocked.py'
    helper.write_text('import time\ntime.sleep(60)\n')
    monkeypatch.setattr(transport, '_WORKER', helper)
    processes = []
    actual_popen = subprocess.Popen
    def popen(*a, **kw):
        process = actual_popen(*a, **kw)
        processes.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', popen)
    started = time.monotonic()
    with pytest.raises(transport.TransportError):
        transport.BoundedHttpTransport()(latitude=46, longitude=7, timeout_seconds=.2)
    assert time.monotonic() - started < 3
    assert len(processes) == 1 and processes[0].poll() is not None


def test_native_child_success(tmp_path, monkeypatch):
    helper = tmp_path / 'success.py'
    helper.write_text('print("{}")\n')
    monkeypatch.setattr(transport, '_WORKER', helper)
    assert transport.BoundedHttpTransport()(latitude=46, longitude=7, timeout_seconds=2) == {}


@pytest.mark.parametrize('kw', [dict(latitude=True), dict(longitude=181),
    dict(timeout_seconds=0), dict(timeout_seconds=float('nan')), dict(timeout_seconds=31)])
def test_invalid_config_before_process(monkeypatch, kw):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('process started'))
    options = dict(latitude=46, longitude=7, timeout_seconds=2)
    options.update(kw)
    with pytest.raises(transport.TransportError): transport.BoundedHttpTransport()(**options)


def test_frozen_fails_closed(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    with pytest.raises(transport.TransportError):
        transport.BoundedHttpTransport()(latitude=46, longitude=7, timeout_seconds=2)


@pytest.mark.parametrize('phase', ['dns', 'connect', 'headers', 'read'])
def test_native_blocked_http_phase_is_killed(tmp_path, monkeypatch, phase):
    helper = tmp_path / 'blocked_http.py'
    marker = tmp_path / 'phase_entered'
    helper.write_text(f'''
import importlib.util
from pathlib import Path
import time
spec = importlib.util.spec_from_file_location('worker', {str(Path(worker.__file__).resolve())!r})
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
def block():
    Path({str(marker)!r}).write_text('entered')
    time.sleep(60)
class Socket:
    def settimeout(self, value): pass
class Connection:
    sock = Socket()
    def __init__(self, *args, **kwargs): pass
    def request(self, *args):
        if {phase!r} in ('dns', 'connect'): block()
    def getresponse(self):
        if {phase!r} == 'headers': block()
        class Response:
            status = 200
            def read1(self, size):
                block()
        return Response()
    def close(self): pass
w.HTTPSConnection = Connection
w.request(46, 7, 1)
''')
    monkeypatch.setattr(transport, '_WORKER', helper)
    processes = []
    actual_popen = subprocess.Popen
    def popen(*a, **kw):
        process = actual_popen(*a, **kw)
        processes.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', popen)
    with pytest.raises(transport.TransportError):
        transport.BoundedHttpTransport()(latitude=46, longitude=7, timeout_seconds=1)
    assert marker.read_text() == 'entered'
    assert len(processes) == 1 and processes[0].poll() is not None


def test_late_success_is_rejected(monkeypatch):
    clock = iter([0, 0, 3])
    monkeypatch.setattr(transport, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k:
        subprocess.CompletedProcess(a, 0, b'{}'))
    with pytest.raises(transport.TransportError):
        transport.BoundedHttpTransport()(latitude=46, longitude=7, timeout_seconds=2)


def test_worker_total_budget_exhausted(monkeypatch):
    factory, calls = connection_factory()
    monkeypatch.setattr(worker, 'HTTPSConnection', factory)
    clock = iter([0, 3])
    monkeypatch.setattr(worker, 'monotonic', lambda: next(clock))
    with pytest.raises(TimeoutError): worker.request(46, 7, 2)
    assert calls[-1] == 'close'


def test_worker_architecture():
    import ast
    for module in (transport, worker):
        tree = ast.parse(Path(module.__file__).read_text())
        imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(any(part in name for part in
            ('tonight', 'opportunity', 'field_lab', 'reference_station', 'thread', 'asyncio'))
            for name in imports)
