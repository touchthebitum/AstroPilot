"""Isolated tool/lock/cache qualification; no product import or packaging/signing command."""
from pathlib import Path
import os,sys,json,subprocess,hashlib,shutil,platform
SOURCE=Path('candidate').resolve();OUT=Path(os.environ['RUNNER_TEMP'])/'setup370-proof';OUT.mkdir(exist_ok=True);MODE=os.environ['PROBE_MODE'];SHA='680090bfa3ceb56ba9394cb97f63942642139322'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==SHA
result={'mode':MODE,'source_sha':SHA,'platform':platform.platform(),'setup_outcome':os.environ['SETUP_OUTCOME'],'cache_hit':os.environ.get('CACHE_HIT',''),'cache_key':os.environ.get('CACHE_KEY',''),'action_uv_version':os.environ.get('ACTION_UV_VERSION',''),'action_uv_path':os.environ.get('ACTION_UV_PATH',''),'action_python_request':os.environ.get('ACTION_PYTHON_VERSION',''),'user_data_used':False,'signing_or_submission':False}
def save(): (OUT/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
if MODE=='invalid_setup':
 assert result['setup_outcome']=='failure';result.update(result='PASS expected setup failure recorded',expected_job_conclusion='failure');save();print(result);sys.exit(0)
assert result['setup_outcome']=='success'
env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME'):
 p=OUT/'environment'/key;p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
env.update(PYTHONUTF8='1',UV_NO_ENV_FILE='1',UV_PROJECT_ENVIRONMENT=str(OUT/'venv-test'))
save()
uv=Path(shutil.which('uv')).resolve();reported_uv=shutil.which(result['action_uv_path']);assert reported_uv and uv==Path(reported_uv).resolve()
version='0.12.6' if MODE=='disabled' else '0.12.5';python_request='3.13.5' if MODE=='disabled' else '3.12'
def call(args,label,expected=0,cwd=SOURCE,e=env):
 r=subprocess.run(args,cwd=cwd,env=e,capture_output=True,text=True,encoding='utf-8',timeout=240)
 (OUT/(label+'.log')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
 if expected is not None:assert r.returncode==expected,(label,r.returncode,r.stderr)
 return r
assert call([str(uv),'--version'],'uv-version').stdout.strip().split()[:2]==['uv',version]
assert result['action_uv_version']==version and result['action_python_request']==python_request
cache=Path(call([str(uv),'cache','dir'],'cache-path').stdout.strip()).resolve();cache.relative_to(Path(os.environ['RUNNER_TEMP']).resolve());canary=cache/'public-setup370-cache-canary.txt'
result.update(uv_version=version,uv_executable=str(uv),cache_path=str(cache),lock_sha256_before=digest(SOURCE/'uv.lock'),pyproject_sha256_before=digest(SOURCE/'pyproject.toml'))
if MODE in ('warm','lock_failure'):
 assert result['cache_hit']=='true' and canary.read_text(encoding='utf-8')=='PUBLIC CACHE RESTORE SENTINEL';result['restored_cache_canary']=True
elif MODE=='cold':assert result['cache_hit'] in ('false','') and not canary.exists()
else:assert result['cache_hit'] in ('false','')
if MODE=='lock_failure':
 fixture=OUT/'stale-lock-fixture';fixture.mkdir();shutil.copy2(SOURCE/'pyproject.toml',fixture/'pyproject.toml');shutil.copy2(SOURCE/'uv.lock',fixture/'uv.lock')
 p=fixture/'pyproject.toml';text=p.read_text(encoding='utf-8');assert 'version = "1.0.0b8"' in text;p.write_text(text.replace('version = "1.0.0b8"','version = "1.0.0b999"',1),encoding='utf-8');old=digest(fixture/'uv.lock')
 bad=env.copy();bad['UV_PROJECT_ENVIRONMENT']=str(OUT/'must-not-sync')
 a=call([str(uv),'lock','--check'],'stale-lock-check',expected=None,cwd=fixture,e=bad);b=call([str(uv),'sync','--locked','--extra','test'],'stale-lock-sync',expected=None,cwd=fixture,e=bad)
 assert a.returncode!=0 and b.returncode!=0 and digest(fixture/'uv.lock')==old
 assert all('lockfile' in r.stderr.lower() and ('needs to be updated' in r.stderr.lower() or 'not up-to-date' in r.stderr.lower()) for r in (a,b)),(a.stderr,b.stderr)
 result.update(result='PASS expected lock failure recorded',expected_job_conclusion='failure',lock_check_exit=a.returncode,locked_sync_exit=b.returncode,fixture_lock_unchanged=True)
 assert digest(SOURCE/'uv.lock')==result['lock_sha256_before'];save();print(result);sys.exit(b.returncode)
call([str(uv),'lock','--check'],'lock-check')
call([str(uv),'sync','--locked','--extra','test'],'sync-test')
command='import sys,json,importlib.metadata as m;print(json.dumps({"version":list(sys.version_info[:3]),"executable":sys.executable,"prefix":sys.prefix,"base_prefix":sys.base_prefix,"pytest":m.version("pytest"),"httpx2":m.version("httpx2"),"pyinstaller_present":any(d.metadata["Name"].lower()=="pyinstaller" for d in m.distributions())}))'
data=json.loads(call([str(uv),'run','--locked','--no-sync','python','-c',command],'python-test').stdout);assert Path(data['prefix']).resolve()==(OUT/'venv-test').resolve() and data['prefix']!=data['base_prefix'];assert data['version'][:2]==([3,13] if MODE=='disabled' else [3,12]);assert not data['pyinstaller_present']
if MODE=='disabled':assert data['version']==[3,13,5]
result['test_interpreter']=data
# A child failure must preserve its code through uv run, even with a healthy lock/cache.
failed=call([str(uv),'run','--locked','--no-sync','python','-c','raise SystemExit(23)'],'child-failure',expected=23);result['child_exit_propagated']=failed.returncode
if MODE=='disabled':
 pack=env.copy();pack['UV_PROJECT_ENVIRONMENT']=str(OUT/'venv-packaging');call([str(uv),'sync','--locked','--extra','packaging'],'sync-packaging',e=pack)
 code='import sys,json,importlib.metadata as m;names={d.metadata["Name"].lower() for d in m.distributions()};print(json.dumps({"version":list(sys.version_info[:3]),"executable":sys.executable,"prefix":sys.prefix,"base_prefix":sys.base_prefix,"pyinstaller":m.version("pyinstaller"),"pytest_present":"pytest" in names,"httpx2_present":"httpx2" in names}))'
 p=json.loads(call([str(uv),'run','--locked','--no-sync','python','-c',code],'python-packaging',e=pack).stdout);assert p['version']==[3,13,5] and not p['pytest_present'] and not p['httpx2_present'];assert Path(p['prefix']).resolve()==(OUT/'venv-packaging').resolve() and p['prefix']!=p['base_prefix'];result['packaging_interpreter']=p
if MODE=='cold':cache.mkdir(parents=True,exist_ok=True);canary.write_text('PUBLIC CACHE RESTORE SENTINEL',encoding='utf-8')
assert digest(SOURCE/'uv.lock')==result['lock_sha256_before'] and digest(SOURCE/'pyproject.toml')==result['pyproject_sha256_before']
result.update(result='PASS',expected_job_conclusion='success',lockfile_and_project_unchanged=True,cache_file_count=sum(p.is_file() for p in cache.rglob('*')))
save();print(result)
