"""Offline boundaries of the explicit real-weather channel; never contacts upstream."""
from contextlib import contextmanager
import json
import socket
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

import pytest
from astropilot import real_weather_context as context
from astropilot import weather_relay as relay

REQUEST = dict(request_id="analysis-1", latitude=46.7508, longitude=6.5495, timezone="Europe/Zurich")


@pytest.fixture(autouse=True)
def inactive(monkeypatch):
    monkeypatch.setattr(context, "_runtime", None)


@pytest.fixture
def local_http(monkeypatch):
    def connect(address, timeout=None, source_address=None):
        assert address[0] == "127.0.0.1"
        sock = socket.socket()
        sock.settimeout(timeout)
        sock.connect(address)
        return sock
    monkeypatch.setattr(socket, "create_connection", connect)


@contextmanager
def running(fetch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    state = relay.RelayState("a" * 64, "b" * 64, fetch=fetch)
    server = relay.relay_server(listener, state)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def post(port, value, *, token="a" * 64, route="/forecast", origin=None):
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + token}
    if origin is not None:
        headers["Origin"] = origin
    req = Request(f"http://127.0.0.1:{port}{route}", data=json.dumps(value).encode(), headers=headers)
    return build_opener(ProxyHandler({})).open(req, timeout=2)


@pytest.mark.parametrize("change", [dict(url="https://example.com"), dict(latitude=True),
    dict(latitude=float("nan")), dict(latitude=10**2000), dict(longitude=181), dict(timezone="../UTC"),
    dict(timezone="Unknown/Zone"), dict(request_id="bad/id"), dict(method="CONNECT")])
def test_invalid_request_never_reaches_upstream(change):
    state = relay.RelayState("a" * 64, "b" * 64, fetch=lambda _: pytest.fail("upstream reached"))
    with pytest.raises(relay.RelayError):
        state.execute({**REQUEST, **change})
    assert not state.seen


@pytest.mark.parametrize("options", [dict(token="wrong"), dict(token="é"), dict(route="/proxy"), dict(origin="http://example.com")])
def test_rpc_rejects_unauthorized_requests(local_http, options):
    with running(lambda _: pytest.fail("upstream reached")) as (port, state):
        with pytest.raises(HTTPError) as error:
            post(port, REQUEST, **options)
        assert error.value.code == 403 and not state.seen


def test_health_rejects_non_ascii_token_without_upstream(local_http):
    with running(lambda _: pytest.fail("upstream reached")) as (port, state):
        request = Request(f"http://127.0.0.1:{port}/health", headers={"Authorization": "Bearer é"})
        with pytest.raises(HTTPError) as error:
            build_opener(ProxyHandler({})).open(request, timeout=2)
        assert error.value.code == 403 and not state.seen


def test_rpc_single_use_and_busy_gate(local_http):
    calls = []
    def fetch(value):
        calls.append(value)
        return dict(payload={}, retrieved_at_utc="2026-11-23T10:00:00+00:00")
    with running(fetch) as (port, state):
        with post(port, REQUEST) as response:
            assert response.headers["X-NightMerit-Relay-Session"] == "b" * 64
            assert json.load(response)["request_id"] == REQUEST["request_id"]
        with pytest.raises(HTTPError):
            post(port, REQUEST)
        with state.gate:
            with pytest.raises(HTTPError):
                post(port, {**REQUEST, "request_id": "analysis-2"})
        assert len(calls) == 1


def test_failed_operation_is_not_retried_and_budget_is_bounded(monkeypatch):
    calls = []
    def fail(value):
        calls.append(value)
        raise relay.RelayError("relay_tls_error")
    state = relay.RelayState("a" * 64, "b" * 64, fetch=fail)
    with pytest.raises(relay.RelayError, match="tls_error"):
        state.execute(REQUEST)
    with pytest.raises(relay.RelayError, match="already_consumed"):
        state.execute(REQUEST)
    monkeypatch.setattr(relay, "MAX_OPERATIONS", 1)
    with pytest.raises(relay.RelayError, match="operation_limit"):
        state.execute({**REQUEST, "request_id": "new"})
    assert len(calls) == 1


def test_absolute_deadline_and_sanitized_audit():
    expired = threading.Event()
    audit = []
    def fetch(_):
        assert expired.wait(1)
        raise RuntimeError("SECRET coordinates 46.7508")
    state = relay.RelayState("a" * 64, "b" * 64, fetch=fetch, expire=expired.set,
                             deadline=.02, audit=lambda **v: audit.append(v))
    with pytest.raises(relay.RelayError, match="unavailable"):
        state.execute(REQUEST)
    assert any(v["category"] == "relay_absolute_timeout" for v in audit)
    assert "SECRET" not in json.dumps(audit) and "46.7508" not in json.dumps(audit)


@pytest.mark.parametrize("status,body,category", [(302, b"{}", "redirect_refused"),
    (503, b"{}", "http_error"), (200, b"[]", "invalid_json"),
    (200, b'{"a":1,"a":2}', "invalid_json"),
    (200, b"x" * (relay.MAX_RESPONSE + 1), "response_too_large")])
def test_upstream_contract_is_fixed_and_bounded(monkeypatch, status, body, category):
    import requests
    class Response:
        status_code = status
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def iter_content(self, size): yield body
    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def mount(self, prefix, adapter):
            assert prefix == "https://" and adapter.max_retries.total == 0
        def get(self, url, **kwargs):
            assert not self.trust_env and url == relay.URL
            assert kwargs["verify"] is True and kwargs["allow_redirects"] is False
            assert kwargs["timeout"] == (5, 15) and kwargs["stream"] is True
            assert kwargs["params"]["forecast_days"] == 7
            assert kwargs["params"]["hourly"].split(",") == list(relay.HOURLY)
            return Response()
    monkeypatch.setattr(requests, "Session", Client)
    with pytest.raises(relay.RelayError, match=category):
        relay.fetch_upstream(REQUEST)


def test_explicit_context_is_single_use_and_reset():
    with pytest.raises(ValueError): context.consume_request()
    with context.explicit_weather_request("analysis-1"):
        assert context.consume_request() == "analysis-1"
        with pytest.raises(ValueError): context.consume_request()
    with pytest.raises(ValueError): context.consume_request()


def test_relay_failure_never_falls_back_to_simulation_or_direct_request(monkeypatch):
    import astro_score
    import astropilot.demo_mode as demo
    context.activate(SimpleNamespace(session_id="b" * 64, location_status=lambda: "available"),
                     relay_port=25001, relay_token="a" * 64)
    monkeypatch.setattr(demo, "_active", True)
    monkeypatch.setattr(demo, "simulated_weather", lambda *_: pytest.fail("simulation fallback"))
    monkeypatch.setattr(relay, "fetch_from_relay", lambda *_: (_ for _ in ()).throw(relay.RelayError("unavailable")))
    assert astro_score.fetch_weather(46.7508, 6.5495) is None


def test_rpc_snapshot_reuses_ingress_and_requires_a_new_explicit_request(local_http, monkeypatch):
    from datetime import datetime, timezone
    from astropilot.demo_mode import simulated_weather
    # Synthetic raw values only: no network and no archive presented as field evidence.
    snapshot = simulated_weather(REQUEST["latitude"], REQUEST["longitude"], REQUEST["timezone"])
    calls = []
    def fetch(value):
        calls.append(value)
        return dict(payload=snapshot.payload, retrieved_at_utc=datetime.now(timezone.utc).isoformat())
    with running(fetch) as (port, _):
        monkeypatch.setattr(context, "_runtime", context.RealWeatherContext("b" * 64, port, "a" * 64))
        with pytest.raises(ValueError):
            relay.fetch_from_relay(REQUEST["latitude"], REQUEST["longitude"], REQUEST["timezone"])
        with context.explicit_weather_request("analysis-1"):
            result = relay.fetch_from_relay(REQUEST["latitude"], REQUEST["longitude"], REQUEST["timezone"])
            assert result.payload == snapshot.payload
            with pytest.raises(ValueError):
                relay.fetch_from_relay(REQUEST["latitude"], REQUEST["longitude"], REQUEST["timezone"])
        assert len(calls) == 1


def test_absolute_timeout_ends_only_the_helper_process():
    import subprocess
    import sys
    script = '''from astropilot.weather_relay import RelayState
import time
state=RelayState('a'*64,'b'*64,fetch=lambda _:time.sleep(10),deadline=.05)
state.execute(dict(request_id='timeout',latitude=46.7508,longitude=6.5495,timezone='Europe/Zurich'))
'''
    result = subprocess.run([sys.executable, "-c", script], timeout=3, capture_output=True)
    assert result.returncode == 124


@pytest.mark.parametrize("assistant", [False, True])
def test_real_fictitious_identity_does_not_load_weather_or_profile(tmp_path, monkeypatch, assistant):
    from fastapi.testclient import TestClient
    from astropilot.launcher_context import LaunchSession
    from astropilot.app import create_app
    from astropilot.profile_transfer_app import create_transfer_app
    kit = tmp_path.resolve() / "Fictitious real weather"
    kit.mkdir()
    profile = kit / "DONNEES-FICTIVES/profil"
    session = LaunchSession("b" * 64, str(kit), str(profile), kit.stat().st_dev, kit.stat().st_ino)
    monkeypatch.setenv("ASTROPILOT_LAUNCH_SESSION", json.dumps(session.__dict__))
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(profile))
    monkeypatch.setenv("NIGHTMERIT_COPY_KIND", "fictitious")
    context.activate(session, relay_port=25001, relay_token="a" * 64)
    def forbidden(*_, **__): pytest.fail("Identity triggered weather or business read")
    app = (create_transfer_app(directory=profile, origin="http://testserver") if assistant else
           create_app(profile_provider=forbidden, weather_provider=forbidden, service_factory=forbidden))
    response = TestClient(app).get("/ui/copy-identity.js")
    identity = json.loads(response.text.split("=", 1)[1].split(";\n", 1)[0])
    assert identity["label"] == "Essai fictif — prévisions réelles"
    assert identity["weather_mode"] == "real" and identity["kind"] == "fictitious"
    assert not profile.exists()
