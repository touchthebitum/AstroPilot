"""Report the actual Python TZif source before importing the application."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import importlib.resources
import io
import json
import os
from pathlib import Path
import zoneinfo
from zoneinfo import ZoneInfo

mode = os.environ['TZ_PROBE_MODE']
assert importlib.metadata.version('tzdata') == '2026.5'
import tzdata
rows = []
for key in ('Europe/Zurich', 'America/Winnipeg'):
    found = next((Path(root) / key for root in zoneinfo.TZPATH if (Path(root) / key).is_file()), None)
    resource = importlib.resources.files('tzdata.zoneinfo').joinpath(*key.split('/'))
    content = found.read_bytes() if found else resource.read_bytes()
    loaded = ZoneInfo.no_cache(key)
    proof = ZoneInfo.from_file(io.BytesIO(content), key=key)
    values = []
    for value in ('2026-03-29T00:50:00+00:00', '2026-03-29T01:10:00+00:00',
                  '2026-10-25T00:10:00+00:00', '2026-10-25T01:10:00+00:00',
                  '2026-10-15T22:30:00+00:00', '2026-11-02T12:00:00+00:00'):
        instant = datetime.fromisoformat(value)
        actual = instant.astimezone(loaded)
        assert actual.isoformat() == instant.astimezone(proof).isoformat()
        values.append({'utc': value, 'local': actual.isoformat(), 'fold': actual.fold})
    rows.append({'key': key, 'source': 'system' if found else 'tzdata-package',
                 'path': str(found or resource), 'sha256': hashlib.sha256(content).hexdigest(), 'values': values})
if mode == 'package':
    assert not zoneinfo.TZPATH and all(x['source'] == 'tzdata-package' for x in rows)
# Product parsing, without replacing its wall-time/DST policy.
from decision.location.location_time import normalize_local_wall_time, normalize_fixed_local_window, LocalWallTimeError
from decision.time_math import add_elapsed_time, elapsed_hours
z = ZoneInfo('Europe/Zurich')
for label, expected in [('2026-03-29T02:30', 'session_availability_local_time_nonexistent'),
                        ('2026-10-25T02:30', 'session_availability_local_time_ambiguous')]:
    try:
        normalize_local_wall_time(label, z)
    except LocalWallTimeError as error:
        assert error.code == expected
    else:
        raise AssertionError('Non-unique wall time must not be accepted')
a, b = normalize_fixed_local_window('2026-10-15T23:30', '2026-10-15T01:30', z)
assert a.isoformat() == '2026-10-15T23:30:00+02:00' and b.isoformat() == '2026-10-16T01:30:00+02:00'
assert elapsed_hours(a, b) == 2
first = datetime(2026, 10, 25, 2, 10, tzinfo=z, fold=1)
assert add_elapsed_time(first, timedelta(minutes=-20)).isoformat() == '2026-10-25T02:50:00+02:00'
result = {'mode': mode, 'package_version': importlib.metadata.version('tzdata'), 'iana_version': tzdata.IANA_VERSION,
          'tzpath': list(zoneinfo.TZPATH), 'rows': rows, 'product_zurich_wall_time_checks': 'PASS'}
Path(os.environ['TZ_PROBE_FILE']).write_text(json.dumps(result, indent=2), encoding='utf-8')
