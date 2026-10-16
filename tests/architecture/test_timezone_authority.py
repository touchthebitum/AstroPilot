"""Locked TZif -> Python/browser parity, including future POSIX rules."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from decision.timezone_authority import _decode, _footer, bundle_json, identity
from tests.timezone_ui_helpers import bootstrap


def node(source):
    executable = shutil.which('node')
    assert executable, 'Node required for timezone parity'
    result = subprocess.run([executable, '-'], input=bootstrap()+source,
                            text=True, encoding='utf-8', capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    return result.stdout


def test_bootstrap_ignores_system_path_and_preexisting_cache():
    script = '''import zoneinfo
before = zoneinfo.ZoneInfo('Europe/Zurich')
import decision
import tzdata
assert zoneinfo.TZPATH == ()
assert zoneinfo.ZoneInfo('Europe/Zurich') is not before
assert zoneinfo.ZoneInfo('Europe/Zurich') is zoneinfo.ZoneInfo('Europe/Zurich')
print(tzdata.__version__)
'''
    result = subprocess.run([sys.executable, '-c', script], env=dict(os.environ),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_every_bundled_zone_at_transitions_and_future():
    data = json.loads(bundle_json())
    # One representative per identical TZif; all links share that decoded record.
    representatives = {digest: zone for zone, digest in data['zones'].items()}
    samples = []
    dates = [datetime(y,m,15,12,tzinfo=timezone.utc) for y in (1900,2026,2040,2100,2500,9998) for m in (1,4,7,11)]
    for digest, zone in representatives.items():
        instants = {int(d.timestamp()) for d in dates}
        for instant, _ in data['rules'][digest]['transitions']:
            instants.update((instant-1,instant,instant+1))
        tz = ZoneInfo(zone)
        for instant in sorted(instants):
            expected = int((datetime(1970,1,1,tzinfo=timezone.utc) + timedelta(seconds=instant)).astimezone(tz).utcoffset().total_seconds())
            samples.append([zone, instant, expected])
    result = json.loads(node('const samples='+json.dumps(samples)+';\n'+'''
const failures=samples.filter(([zone,t,expected])=>NightMeritTime.offsetAt(zone,t*1000)!==expected);
console.log(JSON.stringify({count:samples.length,failures:failures.slice(0,10)}));
'''))
    assert not result['failures'], result
    assert result['count'] > 30000
    assert len(data['zones']) > 500
    assert len(identity()) == 64


@pytest.mark.parametrize('browser_zone', ['Asia/Tokyo','America/Los_Angeles'])
def test_winnipeg_zurich_wall_clock_and_mission(browser_zone, monkeypatch):
    monkeypatch.setenv('TZ', browser_zone)
    source = (Path(__file__).resolve().parents[2]/'astropilot/web/app.js').read_text(encoding='utf-8')
    end = source.index('\nfunction ', source.index('function localDateTimeToUtc(')+10)
    helpers = source[source.index('function localDateTimeParts('):end]
    mission = source[source.index('function missionTimezone('):source.index('function clock(')]
    import tzdata
    at = datetime(2026,11,2,12,tzinfo=timezone.utc)
    local = at.astimezone(ZoneInfo('America/Winnipeg'))
    expected = {'2026.3':'06:00','2026.5':'07:00'}.get(tzdata.__version__, local.strftime('%H:%M'))
    expected_iso = local.isoformat()
    node(helpers+mission+'''
const assert=require('node:assert/strict');
const instant='2026-11-02T12:00:00Z';
'''+f"assert.equal(formatDateTimeLocalInZone(new Date(instant),'America/Winnipeg'),'2026-11-02T{expected}');\n"+f"assert.equal(localDateTimeToUtc('2026-11-02T{expected}','America/Winnipeg'),instant.replace('Z','.000Z'));\n"+'''
assert.equal(formatDateTimeLocalInZone(new Date('2026-10-15T22:30:00Z'),'Europe/Zurich'),'2026-10-16T00:30');
assert.equal(localDateTimeToUtc('2026-10-16T00:30','Europe/Zurich'),'2026-10-15T22:30:00.000Z');
assert.throws(()=>localDateTimeToUtc('2026-03-29T02:30','Europe/Zurich'),/nonexistent_local_datetime/);
assert.throws(()=>localDateTimeToUtc('2026-10-25T02:30','Europe/Zurich'),/ambiguous_local_datetime/);
'''+f"assert(missionDateTimeLabel('{expected_iso}','America/Winnipeg').includes('{expected}'));\n")


@pytest.mark.parametrize('raw',[b'',b'TZif'+bytes(50)])
def test_unsupported_data_rejected(raw):
    with pytest.raises(ValueError): _decode(raw)


def test_unsupported_footer_rejected():
    with pytest.raises(ValueError): _footer('EST5EDT,broken,broken')
