"""Real loopback HTTP plus explicitly injected post-commit response loss."""
import asyncio
from collections import Counter
from contextlib import contextmanager
import http.server
import json
import socket
import threading
from pathlib import Path
import sys

import httpx2 as httpx
import pytest


@contextmanager
def server():
    release = threading.Event()
    calls = Counter()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_args):
            pass

        def do_GET(self):
            calls[self.path] += 1
            if self.path == '/slow':
                self.send_response(200)
                self.send_header('Content-Length', '4')
                self.end_headers()
                self.wfile.flush()
                release.wait(5)
                try:
                    self.wfile.write(b'done')
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                return
            if self.path == '/truncated':
                self.send_response(200)
                self.send_header('Content-Length', '100')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(b'short')
                self.wfile.flush()
                self.close_connection = True
                return
            payload = b'x' * 65536 if self.path == '/stream' else b'OK'
            self.send_response(503 if self.path == '/unavailable' else 200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            try:
                if self.path == '/stream':
                    self.wfile.write(payload[:1024])
                    self.wfile.flush()
                    release.wait(5)
                    self.wfile.write(payload[1024:])
                else:
                    self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            payload = self.rfile.read(int(self.headers['Content-Length']))
            data = json.dumps({'length': self.headers['Content-Length'], 'body': payload.decode()}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}', release, calls
    finally:
        release.set()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_versions():
    import httpcore2
    assert httpx.__version__ == httpcore2.__version__ == '2.13.1'


@pytest.mark.parametrize('path,error', [('/slow', httpx.ReadTimeout), ('/truncated', httpx.RemoteProtocolError)])
def test_transport_failure_then_recovery(path, error):
    with server() as (url, release, calls), httpx.Client(
        trust_env=False, timeout=httpx.Timeout(5, read=.1),
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    ) as client:
        with pytest.raises(error):
            client.get(url + path)
        release.set()
        assert client.get(url + '/ok').text == 'OK'
        assert calls[path] == 1


def test_connection_refused_then_recovery():
    with server() as (url, _release, _calls), httpx.Client(trust_env=False, timeout=5) as client:
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            port = reserved.getsockname()[1]
        # This fixture's own socket is closed, so the local endpoint refuses TCP.
        with pytest.raises(httpx.ConnectError):
            client.get(f'http://127.0.0.1:{port}/')
        assert client.get(url + '/ok').text == 'OK'


def test_http_error_is_not_automatically_retried():
    with server() as (url, _release, calls), httpx.Client(trust_env=False, timeout=5) as client:
        response = client.get(url + '/unavailable')
        with pytest.raises(httpx.HTTPStatusError):
            response.raise_for_status()
        assert calls['/unavailable'] == 1
        assert client.get(url + '/ok').text == 'OK'


def test_raw_upload_respects_file_cursor(tmp_path):
    payload = tmp_path / 'public-upload.bin'
    payload.write_bytes(b'prefix-PAYLOAD')
    with server() as (url, _release, _calls), httpx.Client(trust_env=False, timeout=5) as client, payload.open('rb') as stream:
        stream.seek(7)
        response = client.post(url + '/echo', content=stream)
        assert response.json() == {'length': '7', 'body': 'PAYLOAD'}


def test_abandoned_async_stream_releases_single_connection():
    async def run(url):
        async with httpx.AsyncClient(trust_env=False, timeout=5,
                                     limits=httpx.Limits(max_connections=1, max_keepalive_connections=1)) as client:
            async with client.stream('GET', url + '/stream') as response:
                first = await response.aiter_bytes().__anext__()
                assert 0 < len(first) < 65536
            assert response.is_closed
            assert (await client.get(url + '/ok')).text == 'OK'
    with server() as (url, _release, _calls):
        asyncio.run(run(url))


def test_lost_credit_response_replays_without_double_credit(tmp_path, monkeypatch):
    """Real application credit commits; only its first successful response is dropped."""
    sys.path.insert(0, str(Path.cwd() / 'tests/api'))
    from test_execution_session_api import setup, create_completed
    from astropilot.user_profile import load_user_profile
    fresh = setup(tmp_path, monkeypatch, baseline=0)
    lost = []

    def snapshot():
        return {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*.json')}

    for kind, minutes in (('ha', 90), ('oiii', 15)):
        create_completed(fresh(), f'execution-{kind}', mission_id=f'mission-{kind}',
                         evidence_id=f'evidence-{kind}', minutes=minutes)
        body = {'expected_revision': load_user_profile()['profile_revision'],
                'evidence_ids': [f'evidence-{kind}'], 'confirm_historical_baseline': True}
        url = f'/v1/executions/execution-{kind}/intent-progress-credit'
        client = fresh()
        original = client._transport

        class DropSuccessfulResponse(httpx.BaseTransport):
            def handle_request(self, request):
                response = original.handle_request(request)
                if request.url.path == url:
                    assert response.status_code == 200
                    response.close()
                    lost.append(kind)
                    raise httpx.ReadTimeout('Injected response loss after real credit commit', request=request)
                return response

            def close(self):
                original.close()

        client._transport = DropSuccessfulResponse()
        try:
            with pytest.raises(httpx.ReadTimeout):
                client.post(url, json=body)
        finally:
            client.close()
        before = snapshot()
        # Optimistic concurrency rejects a stale revision without mutation.
        with fresh() as restarted:
            stale = restarted.post(url, json=body)
            assert stale.status_code == 409 and stale.json()['detail']['code'] == 'profile_revision_conflict'
            canonical = restarted.get(f'/v1/executions/execution-{kind}/session')
            assert canonical.status_code == 200 and canonical.json()['credit']
            assert canonical.json()['current_acquired_seconds'] == minutes * 60
        assert snapshot() == before
        # Resume from the canonical read, using the current revision.
        body['expected_revision'] = load_user_profile()['profile_revision']
        for _ in range(3):
            with fresh() as restarted:
                replay = restarted.post(url, json=body)
                assert replay.status_code == 200, replay.text
                assert replay.json()['status'] == 'already_applied'
            assert snapshot() == before
    assert lost == ['ha', 'oiii']
    with fresh() as restarted:
        sessions = restarted.get('/v1/execution-sessions').json()
        assert len(sessions) == 2
        assert {s['acquisition_intent_id']: s['current_acquired_seconds'] for s in sessions} == {
            'sh2-129_ha': 5400, 'ou4_oiii': 900}
