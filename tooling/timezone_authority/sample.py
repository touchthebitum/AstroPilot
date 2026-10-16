"""Read only pure timezone rules, after the production bootstrap."""
import decision
from decision.timezone_authority import bundle_json, identity
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, TZPATH
import tzdata
import io
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
assert TZPATH == ()
rows=[]
for zone in ('America/Winnipeg','Europe/Zurich'):
    raw=files('tzdata.zoneinfo').joinpath(*zone.split('/')).read_bytes()
    independent=ZoneInfo.from_file(io.BytesIO(raw),key=zone)
    loaded=ZoneInfo(zone)
    values=[]
    for at in ('2026-03-29T00:50:00+00:00','2026-03-29T01:10:00+00:00',
               '2026-10-25T00:10:00+00:00','2026-10-25T01:10:00+00:00',
               '2026-10-15T22:30:00+00:00','2026-11-02T12:00:00+00:00'):
        instant=datetime.fromisoformat(at)
        actual=instant.astimezone(loaded).isoformat()
        assert actual == instant.astimezone(independent).isoformat()
        values.append({'utc':at,'local':actual})
    rows.append({'zone':zone,'sha256':hashlib.sha256(raw).hexdigest(),'values':values})
version=tzdata.__version__
assert version == os.environ['EXPECTED_TZDATA']
expected='07:00:00-05:00' if version == '2026.5' else '06:00:00-06:00'
assert rows[0]['values'][-1]['local']=='2026-11-02T'+expected
Path(os.environ['SAMPLE_OUT']).write_text(json.dumps({'version':version,'iana':tzdata.IANA_VERSION,
 'authority_id':identity(),'tzpath':list(TZPATH),'bundle_bytes':len(bundle_json()),'rows':rows},indent=2),encoding='utf-8')
