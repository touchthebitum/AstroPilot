"""Two package versions, native Python + real Chrome, public fixtures only."""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys

SHA='92f3c36c00e1550061ec5aaa9350ce30f19b167b'
SOURCE=Path('candidate').resolve()
OPS=Path('operations/tooling/timezone_authority').resolve()
OUT=Path(os.environ['RUNNER_TEMP'])/'timezone-authority-proof';OUT.mkdir()
LAB=Path(os.environ['RUNNER_TEMP'])/'timezone-authority-lab';LAB.mkdir()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==SHA
base={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
base.pop('PYTHONTZPATH',None)
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME'):
    path=LAB/key;path.mkdir();base[key]=str(path)
base.update(PYTHONUTF8='1',UV_NO_ENV_FILE='1',UV_PROJECT_ENVIRONMENT=str(LAB/'venv'),UV_CACHE_DIR=str(LAB/'uv-cache'))
watched=('uv.lock','pyproject.toml','astropilot/web/app.js','scripts/ci/night_chain/browser.cjs')
hashes={x:hashlib.sha256((SOURCE/x).read_bytes()).hexdigest() for x in watched}
result={'source_sha':SHA,'platform':platform.platform(),'result':'RUNNING','rows':[],'hashes_before':hashes,
 'integration260':'Only an isolated venv receives the hash-pinned #260 wheel; candidate lock/source are not changed.'}
def save(): (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
def call(args,label,env=base):
    with (OUT/(label+'.log')).open('wb') as log:
        run=subprocess.run(args,cwd=SOURCE,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    assert run.returncode==0,(label,run.returncode)
save()
call(['uv','sync','--locked','--extra','test'],'sync')
python=LAB/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
modules=['tests/architecture/'+name+'.py' for name in (
 'test_location_time_trust','test_dst_core_elapsed_time','test_dst_season_presentation',
 'test_session_availability','test_duration_availability_windowing','test_availability_window_preselection',
 'test_mission_site_timezone','test_timezone_authority')]
modules += ['tests/api/test_timezone_authority_transport.py','tests/api/test_configuration_site_guard_ui.py',
 'tests/api/test_execution_session_ui.py','tests/api/test_field_observation_ui.py','tests/api/test_intent_choice_ui.py',
 'tests/api/test_mission_task_times_ui.py','tests/api/test_outcome_evaluation_ui.py','tests/api/test_tonight_ui.py',
 'tests/api/test_tonight_api.py','tests/api/test_tonight_api_e2e.py']
for mode,version in (('locked-main','2026.3'),('integration260','2026.5')):
    env=base.copy();env.update(EXPECTED_TZDATA=version,SAMPLE_OUT=str(OUT/(mode+'-sources.json')),PYTHONPATH=str(SOURCE))
    if version=='2026.5':
        requirements=LAB/'integration260.txt'
        requirements.write_text('https://files.pythonhosted.org/packages/94/21/1e5995a1c920cce14e4bffae20c665ec10e7ed03ab25e006cd741092b718/tzdata-2026.5-py2.py3-none-any.whl --hash=sha256:b683bd1b6659ddcd810ff02ad09ba821d4bf1065072805063eb35c49617905ac\n')
        call(['uv','pip','install','--python',str(python),'--require-hashes','-r',str(requirements)],mode+'-install',env)
    call([str(python),str(OPS/'sample.py')],mode+'-sources',env)
    sample=json.loads(Path(env['SAMPLE_OUT']).read_text(encoding='utf-8'));result['rows'].append(sample);save()
    call([str(python),'-m','pytest','-q',*modules,'--junitxml='+str(OUT/(mode+'-tests.xml'))],mode+'-tests',env)
    # Add read-only observations to the disposable harness, not mocked API responses.
    script=SOURCE/'scripts/ci/night_chain/browser.cjs';original=script.read_bytes();text=original.decode('utf-8')
    anchor="  fs.writeFileSync(path.join(proof, 'browser-result.json'), JSON.stringify({"
    assert text.count(anchor)==1
    observation='''  const timeAuthorityAudit = await evaluate(`({
      id:NightMeritTime.id, version:NightMeritTime.version,
      winnipegClock:clock('2026-11-02T12:00:00Z','America/Winnipeg'),
      winnipegTask:missionTaskTime('T',{window_start:'2026-11-02T12:00:00Z'},'America/Winnipeg'),
      winnipegLocal:formatDateTimeLocalInZone(new Date('2026-11-02T12:00:00Z'),'America/Winnipeg'),
      winnipegUtc:localDateTimeToUtc('2026-11-02TEXPECTED_CLOCK','America/Winnipeg'),
      zurichClock:clock('2026-10-15T22:30:00Z','Europe/Zurich'),
      nativeWinnipeg:new Intl.DateTimeFormat('fr-CH',{timeZone:'America/Winnipeg',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date('2026-11-02T12:00:00Z')),
      userAgent:navigator.userAgent
    })`);
'''.replace('EXPECTED_CLOCK','07:00' if version=='2026.5' else '06:00')
    text=text.replace(anchor,observation+anchor).replace('    ...record, result:','    time_authority_audit:timeAuthorityAudit, ...record, result:')
    browser=env.copy();browser.update(NIGHT_CHAIN_PROOF=str(OUT/(mode+'-browser')),NIGHT_CHAIN_PR_HEAD=SHA,
      BROWSER_NATIVE_HOME=os.environ.get('HOME',''),NODE_BINARY=shutil.which('node'))
    try:
        script.write_text(text,encoding='utf-8')
        call([str(python),'scripts/ci/night_chain/run.py'],mode+'-real-browser',browser)
    finally: script.write_bytes(original)
    reports=list((OUT/(mode+'-browser')).rglob('browser-result.json'));assert len(reports)==3
    for report in reports:
        record=json.loads(report.read_text(encoding='utf-8'));audit=record['time_authority_audit']
        assert record['result']=='PASS' and record['no_execution_or_credit']
        assert audit['id']==sample['authority_id'] and audit['version']==version
        expected='07:00' if version=='2026.5' else '06:00'
        assert audit['winnipegClock']==expected and expected in audit['winnipegTask']
        assert audit['winnipegLocal']=='2026-11-02T'+expected
        assert audit['winnipegUtc']=='2026-11-02T12:00:00.000Z'
        assert audit['zurichClock']=='00:30'
assert result['rows'][0]['authority_id'] != result['rows'][1]['authority_id']
result['hashes_after']={x:hashlib.sha256((SOURCE/x).read_bytes()).hexdigest() for x in watched}
assert result['hashes_after']==hashes
result['result']='PASS';save()
