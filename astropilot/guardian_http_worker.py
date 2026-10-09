"""Single fixed-endpoint HTTPS request. Invoked only by the foreground transport."""
from http.client import HTTPSConnection
import math
import sys
from time import monotonic
from urllib.parse import urlencode

MAX_BODY_BYTES = 65536
_FIELDS = ('rain', 'showers', 'wind_speed_10m', 'wind_gusts_10m',
           'relative_humidity_2m', 'temperature_2m', 'dew_point_2m')


def request(latitude, longitude, timeout_seconds):
    for value, low, high in ((latitude, -90, 90), (longitude, -180, 180),
                             (timeout_seconds, 0, 30)):
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not low <= value <= high):
            raise ValueError()
    if timeout_seconds <= 0:
        raise ValueError()
    deadline = monotonic() + timeout_seconds
    connection = HTTPSConnection('api.open-meteo.com', timeout=timeout_seconds)
    try:
        params = urlencode({'latitude': latitude, 'longitude': longitude,
            'current': ','.join(_FIELDS), 'timezone': 'UTC', 'timeformat': 'unixtime',
            'temperature_unit': 'celsius', 'wind_speed_unit': 'kmh',
            'precipitation_unit': 'mm', 'forecast_days': 1})
        connection.request('GET', '/v1/forecast?' + params)
        def set_remaining():
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError()
            connection.sock.settimeout(remaining)
        set_remaining()
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError()
        body = bytearray()
        while True:
            set_remaining()
            chunk = response.read1(min(4096, MAX_BODY_BYTES + 1 - len(body)))
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                raise ValueError()
            if not chunk:
                break
        if monotonic() >= deadline:
            raise TimeoutError()
        return bytes(body)
    finally:
        connection.close()


if __name__ == '__main__':
    try:
        if len(sys.argv) != 4:
            raise ValueError()
        body = request(*(float(item) for item in sys.argv[1:]))
        sys.stdout.buffer.write(body)
    except Exception:
        sys.exit(1)
