"""Explicit modeled current-weather acquisition; no decision authority."""
from datetime import datetime, timezone
from http.client import HTTPSConnection
import json
import math
import signal
from contextlib import contextmanager
from time import monotonic
from typing import Protocol
from urllib.parse import urlencode

from decision.models.guardian import GuardianEvidence, GuardianObservation

PROVIDER_ID = 'open_meteo_current_v1'
_FIELDS = ('rain', 'showers', 'wind_speed_10m', 'wind_gusts_10m',
           'relative_humidity_2m', 'temperature_2m', 'dew_point_2m')


class GuardianEvidenceProvider(Protocol):
    def __call__(self, logical_time: datetime) -> GuardianObservation: ...


class GuardianAcquisitionError(RuntimeError):
    """Sanitized acquisition failure; runner owns error handling."""


def _number(value, low, high):
    return (type(value) in (int, float) and math.isfinite(value)
            and low <= value <= high)


@contextmanager
def _deadline(seconds):
    # POSIX foreground only: interrupt DNS/connect/header/body without workers.
    if not hasattr(signal, 'setitimer'):
        raise GuardianAcquisitionError('deadline_unavailable')
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise GuardianAcquisitionError('deadline_unavailable')
    def expired(*_):
        raise TimeoutError()
    previous = signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _transport(*, latitude, longitude, timeout_seconds):
    with _deadline(timeout_seconds):
        return _request(latitude=latitude, longitude=longitude, timeout_seconds=timeout_seconds)


def _request(*, latitude, longitude, timeout_seconds):
    deadline = monotonic() + timeout_seconds
    connection = HTTPSConnection('api.open-meteo.com', timeout=timeout_seconds)
    try:
        params = urlencode({'latitude': latitude, 'longitude': longitude,
            'current': ','.join(_FIELDS), 'timezone': 'UTC', 'timeformat': 'unixtime',
            'temperature_unit': 'celsius', 'wind_speed_unit': 'kmh',
            'precipitation_unit': 'mm', 'forecast_days': 1})
        connection.request('GET', '/v1/forecast?' + params)
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError()
        socket = connection.sock
        socket.settimeout(remaining)
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError()
        body = bytearray()
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError()
            socket.settimeout(remaining)
            chunk = response.read1(min(4096, 65537 - len(body)))
            body.extend(chunk)
            if len(body) > 65536:
                raise ValueError()
            if not chunk:
                break
        if monotonic() > deadline:
            raise TimeoutError()
        return json.loads(body)
    finally:
        connection.close()


class ProductionGuardianWeatherAdapter:
    def __init__(self, latitude, longitude, *, timeout_seconds=10, transport=None):
        if (not _number(latitude, -90, 90) or not _number(longitude, -180, 180)
                or not _number(timeout_seconds, 0, 30) or timeout_seconds == 0):
            raise ValueError('weather_config_invalid')
        self.latitude = latitude
        self.longitude = longitude
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _transport

    def __call__(self, logical_time):
        try:
            payload = self._transport(latitude=self.latitude, longitude=self.longitude,
                                      timeout_seconds=self.timeout_seconds)
            if not isinstance(payload, dict):
                raise ValueError()
            current, units = payload.get('current'), payload.get('current_units')
            if not isinstance(current, dict) or not isinstance(units, dict):
                raise ValueError()
            stamp, interval = current.get('time'), current.get('interval')
            if (not _number(stamp, 0, 253402300799)
                    or type(interval) is not int or not 0 < interval <= 3600
                    or units.get('time') != 'unixtime' or units.get('interval') != 'seconds'):
                raise ValueError()
            timestamp = datetime.fromtimestamp(stamp, timezone.utc)
            def value(field, unit, low, high):
                item = current.get(field)
                return item if units.get(field) == unit and _number(item, low, high) else None
            def evidence(item, field):
                if item is None:
                    return None
                return GuardianEvidence(item,
                    f'open-meteo:current:v1:{self.latitude},{self.longitude}:{field}:interval={interval}s',
                    'FORECAST', timestamp)
            rain = value('rain', 'mm', 0, 1000)
            showers = value('showers', 'mm', 0, 1000)
            rain_active = (True if (rain is not None and rain > 0)
                           or (showers is not None and showers > 0)
                           else False if rain == 0 and showers == 0 else None)
            temperature = value('temperature_2m', '°C', -100, 70)
            dew = value('dew_point_2m', '°C', -100, 70)
            return GuardianObservation(
                rain_active=evidence(rain_active, 'rain-and-showers'),
                wind_kmh=evidence(value('wind_speed_10m', 'km/h', 0, 500), 'wind_speed_10m'),
                gust_kmh=evidence(value('wind_gusts_10m', 'km/h', 0, 500), 'wind_gusts_10m'),
                humidity_percent=evidence(value('relative_humidity_2m', '%', 0, 100), 'relative_humidity_2m'),
                dew_spread_c=evidence(None if temperature is None or dew is None
                    else temperature - dew, 'temperature_2m-minus-dew_point_2m'))
        except Exception:
            raise GuardianAcquisitionError('acquisition_failed') from None
