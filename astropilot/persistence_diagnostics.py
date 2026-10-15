"""Best-effort credit persistence diagnostics; never log profile or exception text."""
from datetime import datetime, timezone
import json
import logging
from time import perf_counter

HEADER = "X-Persistence-Diagnostic-ID"
_LOGGER = logging.getLogger("astropilot.launcher.persistence")
_LOGGER.setLevel(logging.INFO)


def log_credit_persistence(event, *, diagnostic_id, category, started, http_status,
                           operation="intent_progress_credit"):
    record = {
        "schema_version": 1,
        "event": event,
        "diagnostic_id": diagnostic_id,
        "occurred_at_utc": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "category": category,
        "duration_ms": round(max(0, perf_counter() - started) * 1000, 3),
        "http_status": http_status,
    }
    try:
        _LOGGER.info("persistence_diagnostic %s", json.dumps(record, sort_keys=True))
    except Exception:
        # A broken diagnostic sink must not change a durable credit or mask refusal.
        pass
