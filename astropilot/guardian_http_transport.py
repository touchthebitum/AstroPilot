"""Portable foreground HTTP deadline: one ephemeral child, always reaped."""
import json
import os
from tempfile import TemporaryDirectory
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
            if timeout_seconds <= 0 or (getattr(sys, 'frozen', False) and sys.platform not in {'darwin', 'win32'}):
                raise ValueError()
            remaining = timeout_seconds - (monotonic() - started)
            if remaining <= 0:
                raise TimeoutError()
            # run kills and waits on TimeoutExpired, on both POSIX and Windows.
            arguments = [str(latitude), str(longitude), str(remaining)]
            with TemporaryDirectory(prefix='astropilot-guardian-') as temporary:
                options = dict(timeout=remaining, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL)
                if getattr(sys, 'frozen', False):
                    output = Path(temporary) / 'weather.json'
                    command = [sys.executable, '--guardian-http-worker', *arguments, str(output)]
                    options['env'] = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
                    options['stdout'] = subprocess.DEVNULL
                    if sys.platform == 'win32':
                        options['creationflags'] = subprocess.CREATE_NO_WINDOW
                else:
                    command = [sys.executable, '-I', str(_WORKER), *arguments]
                result = subprocess.run(command, **options)
                if getattr(sys, 'frozen', False):
                    with output.open('rb') as handle:
                        body = handle.read(MAX_BODY_BYTES + 1)
                else:
                    body = result.stdout
                if len(body) > MAX_BODY_BYTES:
                    raise ValueError()
                payload = json.loads(body, parse_constant=_reject_constant)
            if monotonic() - started >= timeout_seconds:
                raise TimeoutError()
            return payload
        except Exception:
            raise TransportError('acquisition_failed') from None
