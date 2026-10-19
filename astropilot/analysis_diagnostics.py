"""Request timings without locations, payloads or exception messages."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from time import perf_counter
from uuid import uuid4

HEADER = "X-Analysis-Diagnostic-ID"
_LOGGER = logging.getLogger("astropilot.launcher.analysis")
_LOGGER.setLevel(logging.INFO)


class AnalysisTimings:
    def __init__(self):
        self.identifier = uuid4().hex
        self.started = perf_counter()
        self.durations = {}

    @contextmanager
    def measure(self, stage):
        if stage not in {"weather", "calculation"}:
            raise ValueError("unknown analysis timing stage")
        started = perf_counter()
        try:
            yield
        finally:
            self.durations[stage] = max(0, perf_counter() - started) * 1000

    def finish(self, http_status):
        durations = {"total": max(0, perf_counter() - self.started) * 1000,
                     **self.durations}
        record = {
            "schema_version": 1,
            "event": "tonight_complete",
            "diagnostic_id": self.identifier,
            "occurred_at_utc": datetime.now(timezone.utc).isoformat(),
            "http_status": http_status,
            "duration_ms": {key: round(value, 3) for key, value in durations.items()},
        }
        _LOGGER.info("analysis_diagnostic %s", json.dumps(record, sort_keys=True))
        return ", ".join(f"{key};dur={value:.3f}" for key, value in durations.items())
