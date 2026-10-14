"""Weather diagnostics without payloads, URLs, coordinates or exception messages."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from time import perf_counter
from uuid import uuid4

_CURRENT_ID = ContextVar("weather_diagnostic_id", default=None)
_LOGGER = logging.getLogger("astropilot.launcher.weather")
_LOGGER.setLevel(logging.INFO)
HEADER = "X-Weather-Diagnostic-ID"


@contextmanager
def weather_diagnostic_context(diagnostic_id):
    token = _CURRENT_ID.set(diagnostic_id)
    try:
        yield
    finally:
        _CURRENT_ID.reset(token)


def log_weather(event, *, category, started, http_status=None, diagnostic_id=None):
    # A fixed schema deliberately excludes arbitrary exception text and requests.
    record = {
        "schema_version": 1,
        "event": event,
        "diagnostic_id": diagnostic_id or _CURRENT_ID.get() or uuid4().hex,
        "occurred_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "open_meteo",
        "category": category,
        "duration_ms": round(max(0, perf_counter() - started) * 1000, 3),
        "http_status": (http_status if type(http_status) is int and 100 <= http_status <= 599 else None),
    }
    _LOGGER.info("weather_diagnostic %s", json.dumps(record, sort_keys=True))
