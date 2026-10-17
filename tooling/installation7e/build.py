from pathlib import Path,PurePosixPath
import os,sys,subprocess,json,hashlib,shutil,zipfile
SHA='7e98e45b2f46f57dcf959f3bf8d2b1373375cf48';OLD='3cd135644ba8f306c15291073b52c469059247b0'
source=Path('candidate').resolve();ops=Path('operations').resolve();tools=ops/'tooling/installation7e'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==SHA
root=Path(os.environ['RUNNER_TEMP'])/'installation7e';root.mkdir();log=root/'build.log'
env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
if os.name=='nt':env['BROWSER_NATIVE_USERPROFILE']=os.environ['USERPROFILE']
else:env['BROWSER_NATIVE_HOME']=os.environ['HOME']
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','ASTROPILOT_DATA_DIR','UV_CACHE_DIR'):
 p=root/'environment'/key;p.mkdir(parents=True);env[key]=str(p)
env.update(UV_NO_ENV_FILE='1',PYTHONUTF8='1')
def call(args,cwd=source,timeout=900):
 print('Running',args[0],args[1] if len(args)>1 else '',flush=True)
 with log.open('a',encoding='utf-8') as f:
  f.write(repr(args)+'\n');f.flush();subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def unpack(label,expected):
 incoming=Path(os.environ['RUNNER_TEMP'])/label;archive=next(incoming.glob('*.zip'));validation=json.loads((incoming/'kit-validation.json').read_text(encoding='utf-8-sig'));assert validation['source_sha']==expected and sha(archive)==validation['sha256']
 dest=root/label;dest.mkdir()
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 if sys.platform=='darwin':call(['/usr/bin/ditto','-x','-k',str(archive),str(dest)])
 else:
  with zipfile.ZipFile(archive) as z:
   assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in z.namelist());z.extractall(dest)
 return dest/archive.stem
current=unpack('input-current',SHA);previous=unpack('input-previous',OLD)
venv=root/'venv';call(['uv','venv','--python','3.13.5',str(venv)]);python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python');call(['uv','pip','sync','--require-hashes','--python',str(python),str(ops/'tooling/physical70/requirements.txt')])
# Generate public credits through the previous packaged runtime's actual UI/API.
env.update(PRODUCT_SOURCE=str(source),KIT_ROOT=str(previous),KIT_PROOF=str(root/'seed-proof'))
call([str(python),str(ops/'tooling/physical70/selftest.py')],cwd=ops/'tooling/physical70')
seed_case=Path(json.loads((previous/'derniere-copie.json').read_text(encoding='utf-8'))['path']);seed_run=json.loads((seed_case/'run.json').read_text(encoding='utf-8'));assert seed_run['source_sha']==OLD
platform='Windows-x64' if os.name=='nt' else 'Mac-ARM64';kit=root/('NightMerit-Installation-7e98e45-'+platform);shutil.move(current,kit)
shutil.rmtree(kit/'TestController');shutil.rmtree(kit/'Audit')
shutil.copytree(seed_case/'data',kit/'seed',ignore=shutil.ignore_patterns('Logs','*.log'));cdata={p.relative_to(kit/'seed').as_posix():sha(p) for p in (kit/'seed').rglob('*.json')}
(kit/'seed-provenance.json').write_text(json.dumps({'source_sha':OLD,'public_synthetic_only':True,'credits_seconds':{'sh2-129_ha':5400,'ou4_oiii':900},'night_date':seed_run['night_date'],'availability':seed_run['availability'],'files':cdata},indent=2),encoding='utf-8')
if os.name=='nt':
 for label,expected,name in [('official-previous',OLD,'previous-setup.exe'),('official-current',SHA,'candidate-setup.exe')]:
  d=Path(os.environ['RUNNER_TEMP'])/label;meta=json.loads((d/'provenance.json').read_text(encoding='utf-8-sig'));assert meta['source_sha']==expected
  setup=next(d.glob('*setup.exe'));assert sha(setup)==meta['artifacts'][setup.name]['sha256'];shutil.copy2(setup,kit/name);shutil.copy2(d/'provenance.json',kit/(label+'-provenance.json'))
else:
 (kit/'previous').mkdir();call(['/usr/bin/ditto',str(previous/'candidate/AstroPilot.app'),str(kit/'previous/AstroPilot.app')])
 call(['/usr/bin/codesign','--verify','--deep','--strict',str(kit/'previous/AstroPilot.app')])
for p in kit.glob('DEMARRER*'):p.unlink()
for p in kit.glob('REPRENDRE*'):p.unlink()
for p in kit.glob('*signature.txt'):p.unlink()
call([str(python),'-m','unittest','test_safety'],cwd=tools)
call([str(python),'-m','PyInstaller','--noconfirm','--clean','--onedir','--console','--name','TestController','--collect-data','tzdata','--distpath',str(root/'controller-dist'),'--workpath',str(root/'controller-build'),'--specpath',str(root/'controller-spec'),str(tools/'controller.py')],cwd=tools)
shutil.copytree(root/'controller-dist/TestController',kit/'TestController',symlinks=True)
if sys.platform=='darwin':
 for label,p in [('controller',kit/'TestController/TestController'),('mac',kit/'candidate/AstroPilot.app'),('previous',kit/'previous/AstroPilot.app')]:
  call(['/usr/bin/codesign','--verify','--deep','--strict',str(p)]);sig=subprocess.check_output(['/usr/bin/codesign','-d','--verbose=4',str(p)],stderr=subprocess.STDOUT,text=True);assert 'Signature=adhoc' in sig and 'TeamIdentifier=not set' in sig;(kit/(label+'-signature.txt')).write_text(sig)
shutil.copy2(tools/'Guide.html',kit/'Guide.html');shutil.copy2(tools/'LIRE-MOI.txt',kit/'LIRE-MOI.txt');audit=kit/'Audit';audit.mkdir()
for p in tools.iterdir():
 if p.is_file():shutil.copy2(p,audit/p.name)
config=json.loads((kit/'kit.json').read_text());config.update(kind='installation-upgrade-reinstall',baseline_source_sha=OLD,operations_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ops,text=True).strip(),windows_requires_sandbox=True,seed='public_synthetic_preexisting_credits');(kit/'kit.json').write_text(json.dumps(config,indent=2))
if os.name=='nt':
 shutil.copy2(tools/'sandbox-start.cmd',kit/'sandbox-start.cmd')
 import base64
 encoded=base64.b64encode((tools/'launch-sandbox.ps1').read_text().encode('utf-16le')).decode()
 (kit/'LANCER-TEST-WINDOWS.cmd').write_bytes(('@echo off\r\nset "NIGHTMERIT_INSTALL_KIT=%~dp0"\r\npowershell.exe -NoProfile -EncodedCommand '+encoded+'\r\nif errorlevel 1 pause\r\n').encode())
else:
 for name,args in [('LANCER-TEST-MAC.command',''),('REPRENDRE-TEST-MAC.command',' --resume')]:
  p=kit/name;p.write_text('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\n./TestController/TestController'+args+'\ncode=$?\nif [ "$code" -ne 0 ]; then printf "Appuyez sur Entree pour fermer. "; read answer; fi\nexit "$code"\n');p.chmod(0o755)
def inventory():
 rows={}
 for base,dirs,files in os.walk(kit,followlinks=False):
  for name in dirs+files:
   p=Path(base)/name;rel=p.relative_to(kit).as_posix()
   if p.is_symlink():rows[rel]={'link':os.readlink(p)}
   elif p.is_file() and rel!='manifest.json':rows[rel]={'sha256':sha(p)}
 return rows
(kit/'manifest.json').write_text(json.dumps({'source_sha':SHA,'files':inventory()},indent=2))
validation=root/'validation-kit';shutil.copytree(kit,validation,symlinks=True);env.update(INSTALL_KIT=str(validation),INSTALL_PROOF=str(root/'proof'))
call([str(python),str(tools/'selftest.py')],cwd=tools)
assert inventory()==json.loads((kit/'manifest.json').read_text())['files'];assert not (kit/'COPIES-ISOLEES').exists() and not (kit/'RESULTATS').exists()
archive=root/(kit.name+'.zip')
if sys.platform=='darwin':call(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',str(kit),str(archive)])
else:
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for p in kit.rglob('*'):
   if p.is_file():z.write(p,p.relative_to(kit.parent))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
restored=root/'roundtrip';restored.mkdir()
if sys.platform=='darwin':call(['/usr/bin/ditto','-x','-k',str(archive),str(restored)])
else:
 with zipfile.ZipFile(archive) as z:z.extractall(restored)
call([str(restored/kit.name/'TestController'/('TestController.exe' if os.name=='nt' else 'TestController')),'--verify-only'],cwd=restored/kit.name)
if sys.platform=='darwin':call(['/usr/bin/codesign','--verify','--deep','--strict',str(restored/kit.name/'candidate/AstroPilot.app')])
write={'result':'PASS','source_sha':SHA,'baseline_source_sha':OLD,'platform':platform,'kit':archive.name,'sha256':sha(archive),'files':len(inventory()),'pristine':True,'zip_roundtrip_verified':True,'operations_sha':config['operations_sha'],'windows_sandbox_physical_pending':os.name=='nt'}
(root/'kit-validation.json').write_text(json.dumps(write,indent=2));(root/(archive.name+'.sha256')).write_text(sha(archive)+'  '+archive.name+'\n');print(json.dumps(write),flush=True)
