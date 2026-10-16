"""Native runner orchestration. No imports from product before isolated environment."""
from pathlib import Path,PurePosixPath
import os,sys,subprocess,json,hashlib,zipfile
source=Path('candidate').resolve();tools=Path('operations/tooling/packaged_recovery').resolve()
sha=os.environ['APPROVED_SHA'];assert sha=='a5c77a79087e3e50285ec4413b8b643f1f024747'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==sha
root=Path(os.environ['RUNNER_TEMP'])/'packaged-recovery';root.mkdir(exist_ok=False)
env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
if sys.platform=='darwin':env['BROWSER_NATIVE_HOME']=os.environ['HOME']
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','ASTROPILOT_DATA_DIR','UV_CACHE_DIR'):
 p=root/'environment'/key;p.mkdir(parents=True);env[key]=str(p)
env.update(PYTHONUTF8='1',UV_NO_ENV_FILE='1',PRODUCT_SOURCE=str(source),APPROVED_SHA=sha,RECOVERY_PROOF=str(root/'proof'))
def call(args):
 with (root/'bootstrap.log').open('a',encoding='utf-8') as log:
  log.write(repr(args)+'\n');log.flush();subprocess.run(args,env=env,cwd=source,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
if os.name=='nt':
 d=Path(os.environ['RUNNER_TEMP'])/'official-windows';meta=json.loads((d/'provenance.json').read_text(encoding='utf-8-sig'));assert meta['source_sha']==sha
 for name,record in meta['artifacts'].items():assert hashlib.sha256((d/name).read_bytes()).hexdigest()==record['sha256']
 archive=next(d.glob('*portable.zip'));target=root/'payload';target.mkdir()
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in z.namelist())
  z.extractall(target)
 payload=target/'AstroPilot';actual={p.relative_to(payload).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in payload.rglob('*') if p.is_file()}
 assert actual=={r['path']:r['sha256'] for r in meta['portable_inventory']}
 (root/'official-provenance.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
 env['CANDIDATE_EXE']=str(payload/'AstroPilot.exe')
else:
 env['UV_PROJECT_ENVIRONMENT']=str(root/'venv-packaging')
 call(['uv','sync','--locked','--extra','packaging','--python','3.13.5'])
 python=root/'venv-packaging/bin/python'
 call([str(python),'scripts/build_macos.py'])
 call(['/usr/bin/codesign','--verify','--deep','--strict',str(source/'dist/AstroPilot.app')])
 env['CANDIDATE_EXE']=str(source/'dist/AstroPilot.app/Contents/MacOS/AstroPilot')
 (root/'mac-candidate.json').write_text(json.dumps({'sha':sha,'exe_sha256':hashlib.sha256(Path(env['CANDIDATE_EXE']).read_bytes()).hexdigest(),'ad_hoc_codesign_verified':True}),encoding='utf-8')
env['UV_PROJECT_ENVIRONMENT']=str(root/'venv-test')
call(['uv','sync','--locked','--extra','test','--python','3.13.5'])
python=root/('venv-test/Scripts/python.exe' if os.name=='nt' else 'venv-test/bin/python')
call([str(python),str(tools/'qualify.py')])
