"""Explicit, isolated demonstration runtime; never enabled by environment alone."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_active = False
MARKER = '.nightmerit-demo.json'
PROVIDER = 'NightMerit — météo simulée (démonstration)'


def prepare_profile(root: Path) -> None:
    global _active
    root = Path(root)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError('La démonstration exige un dossier absolu séparé.')
    root.mkdir(parents=True, exist_ok=True)
    marker = root / MARKER
    if marker.exists():
        if marker.is_symlink() or json.loads(marker.read_text()) != {'schema': 'nightmerit.demo.v1'}:
            raise ValueError('Marqueur de démonstration invalide ; utilisez un nouveau dossier.')
    else:
        if any(root.iterdir()):
            raise ValueError('Dossier déjà rempli : utilisez un nouveau dossier pour la démonstration.')
        with marker.open('x', encoding='utf-8') as stream:
            json.dump({'schema': 'nightmerit.demo.v1'}, stream)
    _active = True


def context() -> dict:
    return {'enabled': _active, 'weather': 'simulated' if _active else 'real',
            'provider': PROVIDER if _active else None}


def simulated_weather(lat: float, lon: float, zone_name: str):
    from decision.weather.weather_ingress import validate_weather_payload
    now = datetime.now(timezone.utc)
    zone = ZoneInfo(zone_name)
    start = datetime.combine(now.astimezone(zone).date(), time.min, tzinfo=zone).astimezone(timezone.utc)
    count = 192
    values = {'cloud_cover': 0, 'cloud_cover_low': 0, 'cloud_cover_mid': 0,
              'cloud_cover_high': 0, 'precipitation': 0, 'relative_humidity_2m': 50,
              'visibility': 40000, 'wind_speed_10m': 3, 'temperature_2m': 10}
    hourly = {key: [value] * count for key, value in values.items()}
    hourly['time'] = [int((start + timedelta(hours=index)).timestamp()) for index in range(count)]
    units = {key: ('%' if key.startswith('cloud_cover') or key == 'relative_humidity_2m'
                   else {'precipitation': 'mm', 'visibility': 'm', 'wind_speed_10m': 'km/h',
                         'temperature_2m': '°C'}[key]) for key in values}
    units['time'] = 'unixtime'
    payload = {'latitude': lat, 'longitude': lon, 'elevation': 500,
               'timezone': zone_name, 'utc_offset_seconds': int(now.astimezone(zone).utcoffset().total_seconds()),
               'hourly': hourly, 'hourly_units': units}
    snapshot = validate_weather_payload(payload, requested_latitude=lat,
        requested_longitude=lon, requested_timezone=zone_name, retrieved_at_utc=now)
    return replace(snapshot, provider=PROVIDER)


def main(*, port: int = 18831, open_browser: bool = True, isolated_candidate: bool = False) -> None:
    import os
    import socket
    import threading
    import webbrowser
    import uvicorn

    if type(port) is not int or (port not in (18831, 18837, 18841)
            and not (isolated_candidate is True and 20000 <= port <= 65535)):
        raise SystemExit('Port de démonstration non autorisé.')
    raw = os.environ.get('ASTROPILOT_DATA_DIR', '')
    if not raw or not Path(raw).is_absolute():
        raise SystemExit('Choisissez un dossier de démonstration absolu et séparé.')
    for key in tuple(os.environ):
        if key.startswith(('FIELD_LAB_', 'NIGHTMERIT_', 'ASTROPILOT_')) and key not in {'ASTROPILOT_DATA_DIR', 'ASTROPILOT_BUILD_COMMIT'}:
            del os.environ[key]
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Reserve the only allowed port before creating a profile or opening a browser.
        if os.name != 'nt':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', port))
        listener.listen(128)
        prepare_profile(Path(raw))
        # The transfer assistant may already have imported the module singleton
        # before demo activation. Capture runtime identity after activation.
        from astropilot.app import create_app
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port))
        def open_when_ready():
            import time as clock
            for _ in range(120):
                if server.started:
                    webbrowser.open(f'http://127.0.0.1:{port}/')
                    return
                if server.should_exit:
                    return
                clock.sleep(.25)
        if open_browser:
            threading.Thread(target=open_when_ready, daemon=True).start()
        print('DEMONSTRATION : profil fictif et météo simulée. Ctrl+C pour arrêter.', flush=True)
        server.run(sockets=[listener])
    except (OSError, ValueError) as exc:
        raise SystemExit(f'Démonstration non démarrée : {exc}') from None
    finally:
        listener.close()
