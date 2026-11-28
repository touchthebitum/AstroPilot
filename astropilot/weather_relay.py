"""Dedicated loopback RPC; never an arbitrary HTTP proxy.

Only this trusted helper can contact the fixed upstream. The application is
OS-denied outbound except for its helper. The helper's URL restriction is an
application contract, not a DNS-name firewall or same-user security boundary.
"""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import math
import os
import re
import threading
from time import monotonic
from zoneinfo import ZoneInfo

URL = "https://api.open-meteo.com/v1/forecast"
LOCATION_URL = "https://geocoding-api.open-meteo.com/v1/search"
MAX_REQUEST = 4096
MAX_RESPONSE = 1024 * 1024
MAX_OPERATIONS = 512
DEADLINE = 30
HOURLY = ("cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
          "precipitation", "relative_humidity_2m", "visibility", "wind_speed_10m",
          "temperature_2m")


class RelayError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RelayError("relay_invalid_request")
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise RelayError("relay_invalid_json") from error


def validate_request(value):
    if not isinstance(value, dict) or set(value) != {"request_id", "latitude", "longitude", "timezone"}:
        raise RelayError("relay_invalid_request")
    identifier = value["request_id"]
    if not isinstance(identifier, str) or re.fullmatch("[A-Za-z0-9_-]{1,128}", identifier) is None:
        raise RelayError("relay_invalid_request")
    for key, bound in (("latitude", 90), ("longitude", 180)):
        number = value[key]
        if type(number) not in (int, float) or not -bound <= number <= bound or not math.isfinite(number):
            raise RelayError("relay_invalid_request")
    zone = value["timezone"]
    if not isinstance(zone, str) or len(zone) > 128:
        raise RelayError("relay_invalid_request")
    try:
        ZoneInfo(zone)
    except (ValueError, KeyError) as error:
        raise RelayError("relay_invalid_request") from error
    return value


def validate_location_request(value):
    if not isinstance(value, dict) or set(value) != {"request_id", "name"}:
        raise RelayError("relay_invalid_request")
    identifier, name = value["request_id"], value["name"]
    if (not isinstance(identifier, str) or re.fullmatch("[A-Za-z0-9_-]{1,128}", identifier) is None
            or not isinstance(name, str) or not 2 <= len(name.strip()) <= 100
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise RelayError("relay_invalid_request")
    return value


def fetch_location_upstream(value):
    result = _fetch_json(LOCATION_URL, {"name": value["name"].strip(), "count": 8,
                                      "language": "fr", "format": "json"})
    from astropilot.location_search import clean_locations
    try:
        clean_locations(result["payload"])
    except (ValueError, TypeError) as error:
        raise RelayError("relay_invalid_location_response") from error
    return result


def fetch_upstream(value):
    """No environment credentials, redirects, retries or caller-selected URL."""
    params = {"latitude": value["latitude"], "longitude": value["longitude"],
              "timezone": value["timezone"], "forecast_days": 7,
              "temperature_unit": "celsius", "wind_speed_unit": "kmh",
              "precipitation_unit": "mm", "timeformat": "unixtime",
              "hourly": ",".join(HOURLY)}
    return _fetch_json(URL, params)


def _fetch_json(url, params):
    import requests
    try:
        with requests.Session() as client:
            client.trust_env = False
            # Requests' default adapters do not retry; make that contract explicit.
            client.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
            with client.get(url, params=params, timeout=(5, 15), verify=True,
                            allow_redirects=False, stream=True) as response:
                if 300 <= response.status_code < 400:
                    raise RelayError("relay_redirect_refused")
                if response.status_code != 200:
                    raise RelayError("relay_http_error")
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise RelayError("relay_response_too_large")
                payload = decode(raw)
                if not isinstance(payload, dict):
                    raise RelayError("relay_invalid_json")
                return {"payload": payload, "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
    except requests.exceptions.SSLError as error:
        raise RelayError("relay_tls_error") from error
    except requests.exceptions.Timeout as error:
        raise RelayError("relay_timeout") from error
    except requests.exceptions.RequestException as error:
        raise RelayError("relay_connection_error") from error


class RelayState:
    def __init__(self, token, session_id, *, fetch=fetch_upstream, fetch_locations=fetch_location_upstream, expire=None, deadline=DEADLINE, audit=None):
        self.token, self.session_id, self.fetch = token, session_id, fetch
        self.fetch_locations = fetch_locations
        self.expire = expire if expire is not None else lambda: os._exit(124)
        self.deadline = deadline
        self.gate = threading.Lock()
        self.seen = set()
        self.audit = audit if audit is not None else lambda **_: None

    def execute(self, value, *, operation="forecast"):
        if operation == "forecast":
            validate_request(value)
            fetch = self.fetch
        elif operation == "locations":
            validate_location_request(value)
            fetch = self.fetch_locations
        else:
            raise RelayError("relay_invalid_request")
        if not self.gate.acquire(blocking=False):
            raise RelayError("relay_busy")
        try:
            if value["request_id"] in self.seen:
                raise RelayError("relay_request_already_consumed")
            if len(self.seen) >= MAX_OPERATIONS:
                raise RelayError("relay_operation_limit")
            self.seen.add(value["request_id"])
            # DNS/connect/read can exceed a library timeout. Fail closed by ending
            # this helper process; the launcher never automatically restarts it.
            started = monotonic()
            def expired():
                # Never wait for logging on this kill path. Exit code 124 is
                # authoritative even when the journal cannot be written.
                self.expire()
            timer = threading.Timer(self.deadline, expired)
            timer.daemon = True
            timer.start()
            category = "validated_transport"
            try:
                result = fetch(value)
                if len(json.dumps(result, allow_nan=False).encode()) > MAX_RESPONSE + 2048:
                    raise RelayError("relay_response_too_large")
                return result
            except RelayError as error:
                category = str(error)
                raise
            except Exception as error:
                category = "relay_unavailable"
                raise RelayError(category) from error
            finally:
                try:
                    # Keep the deadline armed through synchronous journal I/O.
                    self.audit(category=category, operations=len(self.seen), duration_ms=round((monotonic() - started) * 1000))
                finally:
                    timer.cancel()
        finally:
            self.gate.release()


def relay_server(listener, state):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass  # No URLs, headers, coordinates or token in access logs.

        def reply(self, code, value):
            raw = json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-NightMerit-Relay-Session", state.session_id)
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            self.connection.settimeout(5)
            expected_host = "127.0.0.1:%s" % self.server.server_address[1]
            auth = self.headers.get_all("Authorization", [])
            if (self.path not in {"/forecast", "/locations"} or self.headers.get("Host") != expected_host
                    or self.headers.get("Origin") is not None or len(auth) != 1
                    or not hmac.compare_digest(auth[0].encode("utf-8"), ("Bearer " + state.token).encode("ascii"))):
                self.reply(403, {"error": "relay_access_refused"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            try:
                if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal()
                        or self.headers.get("Transfer-Encoding") is not None
                        or self.headers.get_content_type() != "application/json"):
                    raise RelayError("relay_invalid_request")
                length = int(lengths[0])
                if not 0 < length <= MAX_REQUEST:
                    raise RelayError("relay_request_too_large")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise RelayError("relay_invalid_request")
                value = decode(raw)
                operation = "forecast" if self.path == "/forecast" else "locations"
                result = state.execute(value, operation=operation)
                self.reply(200, {**result, "request_id": value["request_id"]})
            except RelayError as error:
                category = str(error)
                self.reply(503, {"error": category})
            except (OSError, ValueError, TypeError):
                self.reply(503, {"error": "relay_unavailable"})

        def do_GET(self):
            # Readiness is authenticated and strictly local, never upstream.
            if (self.path == "/health" and self.headers.get("Host") == "127.0.0.1:%s" % self.server.server_address[1]
                    and hmac.compare_digest(self.headers.get("Authorization", "").encode("utf-8"), ("Bearer " + state.token).encode("ascii"))):
                self.reply(200, {"ready": True})
            else:
                self.reply(403, {"error": "relay_access_refused"})

    server = ThreadingHTTPServer(listener.getsockname(), Handler, bind_and_activate=False)
    server.socket.close()
    server.socket = listener
    server.server_address = listener.getsockname()
    server.daemon_threads = True
    server.block_on_close = False
    return server


def _request_relay(route, data):
    from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener
    from astropilot.real_weather_context import current
    context = current()
    if context is None or context.relay_port is None:
        raise RelayError("relay_unavailable")
    identifier = data["request_id"]
    request = Request("http://127.0.0.1:%s/%s" % (context.relay_port, route),
                      data=json.dumps(data).encode(), headers={"Content-Type": "application/json",
                      "Authorization": "Bearer " + context.relay_token})
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=32) as reply:
            raw = reply.read(MAX_RESPONSE + 4097)
            if len(raw) > MAX_RESPONSE + 4096 or reply.headers.get("X-NightMerit-Relay-Session") != context.session_id:
                raise RelayError("relay_identity_invalid")
            value = decode(raw)
    except OSError as error:
        raise RelayError("relay_unavailable") from error
    if not isinstance(value, dict) or set(value) != {"payload", "retrieved_at_utc", "request_id"} or value["request_id"] != identifier:
        raise RelayError("relay_identity_invalid")
    try:
        retrieved = datetime.fromisoformat(value["retrieved_at_utc"])
        if retrieved.tzinfo is None or retrieved.utcoffset() != timezone.utc.utcoffset(retrieved):
            raise ValueError()
    except (TypeError, ValueError) as error:
        raise RelayError("relay_invalid_timestamp") from error
    return value, retrieved


def fetch_locations_from_relay(name):
    import secrets
    data = {"request_id": "location-" + secrets.token_hex(16), "name": name}
    validate_location_request(data)
    value, _ = _request_relay("locations", data)
    return value["payload"]


def fetch_from_relay(latitude, longitude, timezone_name):
    from astropilot.real_weather_context import consume_request
    from decision.weather.weather_ingress import validate_weather_payload
    identifier = consume_request()
    data = {"request_id": identifier, "latitude": latitude, "longitude": longitude, "timezone": timezone_name}
    validate_request(data)
    value, retrieved = _request_relay("forecast", data)
    return validate_weather_payload(value["payload"], requested_latitude=latitude,
        requested_longitude=longitude, requested_timezone=timezone_name, retrieved_at_utc=retrieved)
