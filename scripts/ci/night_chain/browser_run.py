"""One isolated application + browser, followed by a fresh application reread."""
from common import CASE, ROOT, TestClient, app, profile_hash, seed
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

PROOF = Path(os.environ['CASE_PROOF'])
seed()
before = profile_hash()
with socket.socket() as available:
    available.bind(('127.0.0.1', 0))
    port = available.getsockname()[1]
url = f'http://127.0.0.1:{port}'
env = {**os.environ, 'NIGHT_CHAIN_URL': url}
with (PROOF / 'server.log').open('wb') as log:
    child = subprocess.Popen(
        [sys.executable, '-B', '-m', 'uvicorn', 'server:application',
         '--app-dir', str(Path(__file__).parent), '--host', '127.0.0.1', '--port', str(port)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(200):
            assert child.poll() is None, 'Server exited before browser navigation'
            try:
                with urllib.request.urlopen(url + '/__ci/provenance', timeout=1) as response:
                    assert json.load(response) == {
                        'case': CASE.name, 'source_sha': os.environ['NIGHT_CHAIN_SOURCE_SHA']}
                break
            except OSError:
                time.sleep(.2)
        else:
            raise AssertionError('Server startup timeout')
        browser = subprocess.Popen(
            [os.environ.get('NODE_BINARY', 'node'), str(Path(__file__).with_name('browser.cjs'))], env=env)
        try:
            code = browser.wait(timeout=180)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(browser.pid), '/T', '/F'], timeout=15)
            else:
                browser.kill()  # The outer case supervisor also removes the private process group.
            browser.wait(timeout=15)
            raise
        assert code == 0, 'Browser scenario failed; see CDP log'
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)
        assert child.poll() is not None
# The browser has stopped; seed is never called again during the reread.
record = json.loads((PROOF / 'browser-result.json').read_text(encoding='utf-8'))
with TestClient(app()) as client:
    current = client.get('/v1/accepted-mission/current')
    assert current.status_code == 200, current.text
    record['current_after_restart'] = current.json()
    (PROOF / 'browser-result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    if os.environ['UI_INTENT'] == 'site_changed':
        assert current.json() is None
        assert profile_hash() != before
        assert client.get('/v1/configuration').json()['site']['latitude'] == 46.9
    else:
        assert profile_hash() == before
        assert current.json()['mission'] == record['accepted']['body']['mission']
        assert current.json()['mission_id'] == record['accepted']['body']['mission_id']
        start = datetime.fromisoformat(current.json()['mission']['window_start'])
        end = datetime.fromisoformat(current.json()['mission']['window_end'])
        assert datetime.fromisoformat('2026-10-16T00:30:00+02:00') <= start < end
        assert end <= datetime.fromisoformat('2026-10-16T03:30:00+02:00')
    sessions = client.get('/v1/execution-sessions')
    assert sessions.status_code == 200 and sessions.json() == [], sessions.text
    profile = json.loads((CASE / 'data/user_profile.json').read_text(encoding='utf-8'))
    assert not profile.get('intent_progress_credits')
    assert not (CASE / 'data/user_filters.json').exists()
record.update(restart_mission_preserved=True, no_execution_or_credit=True,
              profile_unchanged=os.environ['UI_INTENT'] != 'site_changed',
              server_stopped=True, source_sha=os.environ['NIGHT_CHAIN_SOURCE_SHA'])
(PROOF / 'browser-result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print('Browser journey PASS:', os.environ['UI_INTENT'])
