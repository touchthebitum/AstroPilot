"""Portable foreground HTTP deadline: one ephemeral child, always reaped."""
import json
import math
from pathlib import Path
import subprocess
import sys
from time import monotonic

_WORKER = Path(__file__).with_name('guardian_http_worker.py').resolve()
MAX_BODY_BYTES = 65536


class TransportError(RuntimeError):
    """No upstream URLs, payloads or exception details escape this boundary."""


def _reject_constant(_):
    raise ValueError()


class BoundedHttpTransport:
    def __call__(self, *, latitude, longitude, timeout_seconds):
        started = monotonic()
        try:
            for value, low, high in ((latitude, -90, 90), (longitude, -180, 180),
                                     (timeout_seconds, 0, 30)):
                if (type(value) not in (int, float) or not math.isfinite(value)
                        or not low <= value <= high):
                    raise ValueError()
            if timeout_seconds <= 0 or getattr(sys, 'frozen', False):
                raise ValueError()
            remaining = timeout_seconds - (monotonic() - started)
            if remaining <= 0:
                raise TimeoutError()
            # run kills and waits on TimeoutExpired, on both POSIX and Windows.
            result = subprocess.run(
                [sys.executable, '-I', str(_WORKER), str(latitude), str(longitude),
                 str(remaining)], timeout=remaining, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL)
            if len(result.stdout) > MAX_BODY_BYTES:
                raise ValueError()
            payload = json.loads(result.stdout, parse_constant=_reject_constant)
            if monotonic() - started >= timeout_seconds:
                raise TimeoutError()
            return payload
        except Exception:
            raise TransportError('acquisition_failed') from None
