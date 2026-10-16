"""Native, bounded timezone qualification of PR260; no profile import in parent."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile

SHA = '136b40068605069c6ec5e50686891fa950faa349'
SOURCE = Path('candidate').resolve()
OPS = Path('operations/tooling/tzdata260').resolve()
OUT = Path(os.environ['RUNNER_TEMP']) / 'tzdata260-proof'
OUT.mkdir()
LAB = Path(os.environ['RUNNER_TEMP']) / 'tzdata260-lab'
LAB.mkdir()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip() == SHA
base = {k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
base.pop('PYTHONTZPATH', None)
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME'):
    p = LAB / key; p.mkdir(); base[key] = str(p)
base.update(PYTHONUTF8='1',UV_NO_ENV_FILE='1',UV_PROJECT_ENVIRONMENT=str(LAB/'venv'),UV_CACHE_DIR=str(LAB/'uv-cache'))
watched = ('uv.lock','pyproject.toml','astropilot/web/app.js','scripts/ci/night_chain/browser.cjs')
hashes = {x:hashlib.sha256((SOURCE/x).read_bytes()).hexdigest() for x in watched}
result = {'source_sha':SHA,'platform':platform.platform(),'result':'RUNNING','rows':[],'divergences':[],'hashes_before':hashes}
def save(): (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
def call(args,label,env=base):
    with (OUT/(label+'.log')).open('wb') as log:
        r = subprocess.run(args,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=480)
    assert r.returncode == 0, (label,r.returncode)
save()
call(['uv','sync','--locked','--extra','test'],'sync')
python = LAB/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
# Initial sys.path is the product checkout; sample then imports the production functions.
modules = ['tests/architecture/'+name+'.py' for name in (
 'test_location_time_trust','test_dst_core_elapsed_time','test_dst_season_presentation',
 'test_session_availability','test_duration_availability_windowing','test_availability_window_preselection',
 'test_mission_site_timezone')]
modules += ['tests/api/test_mission_task_times_ui.py','tests/api/test_configuration_site_guard_ui.py',
            'tests/api/test_tonight_api.py','tests/api/test_tonight_api_e2e.py']
for mode in ('default','package'):
    env = base.copy()
    if mode == 'package': env['PYTHONTZPATH'] = ''
    env.update(TZ_PROBE_MODE=mode,TZ_PROBE_FILE=str(OUT/(mode+'-sources.json')),PYTHONPATH=str(SOURCE))
    call([str(python),str(OPS/'sample.py')],mode+'-sources',env)
    data = json.loads((OUT/(mode+'-sources.json')).read_text(encoding='utf-8'))
    result['rows'].append(data);save()
    call([str(python),'-m','pytest','-q',*modules,'--junitxml='+str(OUT/(mode+'-tests.xml'))],mode+'-tests',env)
# Compare the changed zone to the old wheel whose URL/hash are pinned in main's 2026.3 lock.
url='https://files.pythonhosted.org/packages/e5/6d/b53b99a9f2766d095985947a5782f1702cabb129a34f7a802d7197af832f/tzdata-2026.3-py2.py3-none-any.whl'
with urllib.request.urlopen(url,timeout=30) as remote: old=remote.read(1024*1024)
assert hashlib.sha256(old).hexdigest() == 'dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931'
with zipfile.ZipFile(io.BytesIO(old)) as archive:
    assert archive.testzip() is None
    old_file=LAB/'old-winnipeg.tzif';old_file.write_bytes(archive.read('tzdata/zoneinfo/America/Winnipeg'))
code='''from zoneinfo import ZoneInfo
from datetime import datetime,timezone
import json,sys
with open(sys.argv[1],'rb') as f: old=ZoneInfo.from_file(f,key='America/Winnipeg')
new=ZoneInfo('America/Winnipeg'); at=datetime(2026,11,2,12,tzinfo=timezone.utc)
a=at.astimezone(old).isoformat(); b=at.astimezone(new).isoformat()
assert a=='2026-11-02T06:00:00-06:00' and b=='2026-11-02T07:00:00-05:00'
print(json.dumps({'old_2026_3':a,'new_2026_5':b}))'''
forced=base.copy();forced['PYTHONTZPATH']=''
comparison=subprocess.check_output([str(python),'-c',code,str(old_file)],cwd=SOURCE,env=forced,text=True,encoding='utf-8',timeout=30)
result['expected_upstream_change']=json.loads(comparison);save()
# Real browser/HTTP journeys with the candidate package actually used by Python.
# Add a read-only Intl observation to the disposable browser harness, restoring it afterwards.
script=SOURCE/'scripts/ci/night_chain/browser.cjs';original=script.read_bytes();text=original.decode('utf-8')
anchor="  fs.writeFileSync(path.join(proof, 'browser-result.json'), JSON.stringify({"
assert text.count(anchor)==1
observation='''  const timeDatabaseAudit = await evaluate(`({
    winnipegClock: clock('2026-11-02T12:00:00Z','America/Winnipeg'),
    winnipegTask: missionTaskTime('T', {window_start:'2026-11-02T07:00:00-05:00'}, 'America/Winnipeg'),
    zurichClock: clock('2026-10-15T22:30:00Z','Europe/Zurich'),
    userAgent:navigator.userAgent,
  })`);
'''
text=text.replace(anchor,observation+anchor).replace('    ...record, result:', '    time_database_audit: timeDatabaseAudit, ...record, result:')
assert text != original.decode('utf-8')
browser=forced.copy();browser.update(NIGHT_CHAIN_PROOF=str(OUT/'browser'),NIGHT_CHAIN_PR_HEAD=SHA,
 BROWSER_NATIVE_HOME=os.environ.get('HOME',''),NODE_BINARY=shutil.which('node'))
try:
    script.write_text(text,encoding='utf-8')
    call([str(python),'scripts/ci/night_chain/run.py'],'real-browser',browser)
finally:
    script.write_bytes(original)
for p in (OUT/'browser').rglob('browser-result.json'):
    record=json.loads(p.read_text(encoding='utf-8'));assert record['result']=='PASS' and record['no_execution_or_credit']
    audit=record['time_database_audit']
    if audit['winnipegClock']!='07:00':
        result['divergences'].append({'scope':'Chrome Intl vs tzdata2026.5','journey':record['intent'],**audit,'expected_clock':'07:00'})
result['hashes_after']={x:hashlib.sha256((SOURCE/x).read_bytes()).hexdigest() for x in watched}
assert result['hashes_after']==hashes
result['result']='PASS' if not result['divergences'] else 'BLOCKED_TIME_DATABASE_DIVERGENCE'
save()
if result['divergences']:raise SystemExit(1)
