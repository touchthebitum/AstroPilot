"""Disposable real Uvicorn startup/shutdown qualification; no personal profiles."""
from pathlib import Path
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

OUT = Path(os.environ['LIFECYCLE_PROOF']).resolve()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
SOURCE = Path(os.environ['PRODUCT_SOURCE']).resolve()


def snapshot(data):
    return {p.relative_to(data).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in data.rglob('*') if p.is_file() and 'Logs' not in p.relative_to(data).parts}


def child():
    import uvicorn
    from astropilot import launcher
    assert uvicorn.__version__ == '0.54.0'
    shutdown = threading.Event()
    done = threading.Event()

    def watcher():
        while not done.wait(.05):
            if (OUT / 'stop-requested').exists():
                shutdown.set()
                return

    def config(app, **kwargs):
        value = uvicorn.Config(app, **kwargs)
        value.load()
        assert value.http_protocol_class.__module__ == 'uvicorn.protocols.http.h11_impl'
        return value

    worker = threading.Thread(target=watcher, daemon=True)
    worker.start()
    try:
        launcher.run(shutdown_event=shutdown, config_factory=config,
                     browser_open=lambda url: (OUT / 'browser-request.json').write_text(json.dumps({'url': url})))
    finally:
        done.set()
        worker.join(timeout=1)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    data = OUT / 'data'
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('ASTROPILOT_', 'NIGHTMERIT_', 'FIELD_LAB_'))}
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TMP', 'TEMP', 'TMPDIR',
                'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME'):
        directory = OUT / 'environment' / key
        directory.mkdir(parents=True)
        env[key] = str(directory)
    env.update(ASTROPILOT_DATA_DIR=str(data), PYTHONUTF8='1',
               LIFECYCLE_PROOF=str(OUT), PRODUCT_SOURCE=str(SOURCE))
    # Check the listener before starting any child; never connect to a preexisting app.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8000))
    before = None
    cycles = []
    for cycle in range(2):
        (OUT / 'stop-requested').unlink(missing_ok=True)
        (OUT / 'browser-request.json').unlink(missing_ok=True)
        child_process = None
        with (OUT / f'cycle-{cycle}.log').open('wb') as log:
            try:
                child_process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--child'],
                                                 cwd=SOURCE, env=env, stdout=log, stderr=log)
                deadline = time.monotonic() + 30
                while not (OUT / 'browser-request.json').exists():
                    assert child_process.poll() is None, 'Owned launcher exited before readiness'
                    assert time.monotonic() < deadline, 'Readiness deadline'
                    time.sleep(.05)
                with OPENER.open('http://127.0.0.1:8000/v1/runtime-identity', timeout=10) as response:
                    identity = json.load(response)
                assert identity['application'] == 'astropilot'
                if cycle == 0:
                    body = json.dumps({'expected_revision': 0, 'site': {'name': 'PUBLIC RUNTIME TEST', 'latitude': 46.9,
                                               'longitude': 6.6, 'bortle': 4},
                                       'equipment': {'preset_id': 'samyang_183'},
                                       'projects': {'Sh2-129': {'hours': 0, 'target_hours': 6, 'importance': 5}}}).encode()
                    request = urllib.request.Request('http://127.0.0.1:8000/v1/configuration', data=body,
                                                     headers={'Content-Type': 'application/json'}, method='PUT')
                    with OPENER.open(request, timeout=10) as response:
                        assert response.status == 200
                connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=10)
                try:
                    connection.request('GET', '/v1/configuration', headers={'Connection': 'keep-alive, CLOSE'})
                    response = connection.getresponse()
                    assert response.status == 200 and response.will_close
                    assert json.loads(response.read())['site']['name'] == 'PUBLIC RUNTIME TEST'
                finally:
                    connection.close()
                if before is None:
                    before = snapshot(data)
                else:
                    assert snapshot(data) == before, 'Restart changed canonical data'
                (OUT / 'stop-requested').touch()
                assert child_process.wait(timeout=20) == 0, 'Graceful shutdown failed'
                with socket.socket() as probe:
                    assert probe.connect_ex(('127.0.0.1', 8000)) != 0, 'Listener remains after shutdown'
                assert snapshot(data) == before, 'Shutdown changed canonical data'
                cycles.append({'ready': True, 'graceful_exit_code': 0, 'port_released': True,
                               'connection_close_tokens': True, 'canonical_bytes_unchanged': True})
            finally:
                if child_process and child_process.poll() is None:
                    # Only this child; cleanup is never counted as a passing graceful stop.
                    child_process.terminate()
                    child_process.wait(timeout=10)
    result = {'result': 'PASS', 'uvicorn': '0.54.0', 'http_implementation': 'h11',
              'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip(),
              'cycles': cycles, 'physical_user_test': False}
    (OUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    child() if '--child' in sys.argv else main()
