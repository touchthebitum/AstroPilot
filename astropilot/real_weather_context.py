"""Explicit launch context and single-use analysis scope for the real-weather kit."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RealWeatherContext:
    session_id: str
    relay_port: int | None = None
    relay_token: str | None = None


_runtime = None
_request = ContextVar("real_weather_request", default=None)


def activate(session, *, relay_port=None, relay_token=None):
    global _runtime
    if session is None or session.location_status() != "available":
        raise ValueError("real_weather_launch_identity_invalid")
    if relay_port is not None and (type(relay_port) is not int or not 20000 <= relay_port <= 65535):
        raise ValueError("real_weather_relay_port_invalid")
    if relay_token is not None and re.fullmatch("[0-9a-f]{64}", relay_token) is None:
        raise ValueError("real_weather_relay_token_invalid")
    if (relay_port is None) != (relay_token is None):
        raise ValueError("real_weather_relay_identity_incomplete")
    _runtime = RealWeatherContext(session.session_id, relay_port, relay_token)


def current():
    return _runtime


@contextmanager
def explicit_weather_request(identifier):
    # This scope is opened only by the explicit analysis endpoint, never startup.
    value = {"id": identifier, "used": False}
    token = _request.set(value)
    try:
        yield
    finally:
        _request.reset(token)


def consume_request():
    value = _request.get()
    if (value is None or value["used"] or not isinstance(value["id"], str)
            or re.fullmatch("[A-Za-z0-9_-]{1,128}", value["id"]) is None):
        raise ValueError("real_weather_explicit_request_required")
    value["used"] = True
    return value["id"]
