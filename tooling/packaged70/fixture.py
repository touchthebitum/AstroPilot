"""Public deterministic fixture. Isolate paths before importing the product."""
from datetime import datetime, timedelta
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(os.environ['PRODUCT_SOURCE'])
CASE = Path(os.environ['CASE_ROOT']).resolve()
assert (CASE / 'QUALIFICATION_ONLY').is_file()
for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TMP', 'TEMP',
            'TMPDIR', 'ASTROPILOT_DATA_DIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME',
            'XDG_DATA_HOME', 'MPLCONFIGDIR'):
    directory = CASE / ('data' if key == 'ASTROPILOT_DATA_DIR' else key)
    directory.mkdir(exist_ok=True)
    os.environ[key] = str(directory)
sys.path.insert(0, str(ROOT))

# A regression must not turn this fixture into a live weather/network test.
_connect = socket.socket.connect

def loopback_connect(sock, address):
    if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
        return _connect(sock, address)
    raise AssertionError('Only numeric loopback connections are allowed in this fixture')

socket.socket.connect = loopback_connect

from fastapi.testclient import TestClient
from astropilot.app import create_app
import astro_score
from decision.weather.weather_ingress import REQUIRED_HOURLY_UNITS, validate_weather_payload

REFERENCE = datetime.now(__import__('datetime').timezone.utc)

def weather():
    start = REFERENCE.replace(hour=0)
    count = 192
    payload = {
        'latitude': float(os.environ['SITE_LAT']), 'longitude': float(os.environ['SITE_LON']), 'elevation': 837.,
        'timezone': os.environ['SITE_ZONE'], 'utc_offset_seconds': int(REFERENCE.astimezone(__import__('zoneinfo').ZoneInfo(os.environ['SITE_ZONE'])).utcoffset().total_seconds()),
        'hourly_units': {'time': 'unixtime', **REQUIRED_HOURLY_UNITS},
        'hourly': {
            'time': [int((start + timedelta(hours=i)).timestamp()) for i in range(count)],
            **{key: [value] * count for key, value in {
                'cloud_cover': 0., 'cloud_cover_low': 0., 'cloud_cover_mid': 0.,
                'cloud_cover_high': 0., 'precipitation': 0., 'relative_humidity_2m': 40.,
                'visibility': 40000., 'wind_speed_10m': 3., 'temperature_2m': 10.,
            }.items()},
        },
    }
    return validate_weather_payload(
        payload, requested_latitude=float(os.environ['SITE_LAT']), requested_longitude=float(os.environ['SITE_LON']),
        requested_timezone=os.environ['SITE_ZONE'], retrieved_at_utc=REFERENCE - timedelta(minutes=5))

WEATHER = weather()

def factory():
    service = astro_score.build_durable_tonight_application_service()
    service.clock = lambda: REFERENCE
    return service

def app():
    return create_app(service_factory=factory, weather_provider=lambda *_: WEATHER,
                      clock=lambda: REFERENCE, guardian_renewal_enabled=False)

def profile_hash():
    return hashlib.sha256((CASE / 'data/user_profile.json').read_bytes()).hexdigest()

def seed():
    with TestClient(app()) as client:
        response = client.put('/v1/configuration', json={
            'expected_revision': 0,
            'site': {'name': 'PUBLIC CI FIXTURE', 'latitude': float(os.environ['SITE_LAT']), 'longitude': float(os.environ['SITE_LON']), 'bortle': 4},
            'equipment': {'preset_id': 'samyang_183'},
            'projects': {'Sh2-129': {'hours': 0, 'target_hours': 20, 'importance': 9}},
        })
        assert response.status_code == 200, response.text
        response = client.put('/v1/projects/Sh2-129/progress', json={
            'expected_revision': response.json()['profile_revision'],
            'imaging_field_id': 'sh2-129_ou4',
            'acquisition_intent_progress': [
                {'acquisition_intent_id': intent, 'acquired_duration_manual': 0}
                for intent in ('sh2-129_ha', 'ou4_oiii')],
            'acquisition_intent_targets': [
                {'acquisition_intent_id': intent, 'target_hours': 6}
                for intent in ('sh2-129_ha', 'ou4_oiii')],
        })
        assert response.status_code == 200, response.text
    assert not (CASE / 'data/user_filters.json').exists()
