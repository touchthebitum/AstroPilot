"""Build and qualify two autonomous internal test kits; exact main product sources."""
from pathlib import Path,PurePosixPath
import os,sys,subprocess,json,hashlib,shutil,zipfile
SHA='7bc3170919589fdbb0e59e38d29cf13738e0e0e8'
source=Path('candidate').resolve();tools=Path('operations/tooling/physical70').resolve();ops=Path('operations').resolve()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==SHA
subprocess.run(['git','diff','--exit-code','HEAD'],cwd=source,check=True)
root=Path(os.environ['RUNNER_TEMP'])/'physical70';root.mkdir();platform='Windows-x64' if os.name=='nt' else 'Mac-ARM64';kit=root/('NightMerit-Test-7bc3170-'+platform);kit.mkdir()
env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
if sys.platform=='darwin':env['BROWSER_NATIVE_HOME']=os.environ['HOME']
if os.name=='nt':env['BROWSER_NATIVE_USERPROFILE']=os.environ['USERPROFILE']
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','ASTROPILOT_DATA_DIR','UV_CACHE_DIR'):
 p=root/'environment'/key;p.mkdir(parents=True);env[key]=str(p)
env.update(UV_NO_ENV_FILE='1',PYTHONUTF8='1')
log=root/'build.log'
def call(args,cwd=source,timeout=600):
 print('Running',args[0],args[1] if len(args)>1 else '',flush=True)
 with log.open('a',encoding='utf-8') as f:
  f.write(repr(args)+'\n');f.flush();subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if os.name=='nt':
 d=Path(os.environ['RUNNER_TEMP'])/'official-windows';meta=json.loads((d/'provenance.json').read_text(encoding='utf-8-sig'));assert meta['source_sha']==SHA;assert next(x['version'] for x in meta['installed_distributions'] if x['name'].lower()=='uvicorn')=='0.54.0'
 archive=next(d.glob('*portable.zip'));assert sha(archive)==meta['artifacts'][archive.name]['sha256']
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None and all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in z.namelist());z.extractall(root/'portable')
 payload=root/'portable/AstroPilot';assert {p.relative_to(payload).as_posix():sha(p) for p in payload.rglob('*') if p.is_file()}=={r['path']:r['sha256'] for r in meta['portable_inventory']}
 shutil.move(str(payload),str(kit/'candidate'));shutil.copy2(d/'provenance.json',kit/'product-provenance.json')
else:
 env['UV_PROJECT_ENVIRONMENT']=str(root/'venv-product');call(['uv','sync','--locked','--extra','packaging','--python','3.13.5']);python=root/'venv-product/bin/python'
 call([str(python),'-c',"import uvicorn;assert uvicorn.__version__=='0.54.0';print(uvicorn.__version__)"])
 call([str(python),'scripts/build_macos.py']);app=source/'dist/AstroPilot.app'
 call(['/usr/bin/codesign','--verify','--deep','--strict',str(app)])
 signature=subprocess.check_output(['/usr/bin/codesign','-d','--verbose=4',str(app)],stderr=subprocess.STDOUT,text=True);assert 'Signature=adhoc' in signature and 'TeamIdentifier=not set' in signature
 (kit/'candidate').mkdir();call(['/usr/bin/ditto',str(app),str(kit/'candidate/AstroPilot.app')]);(kit/'mac-signature.txt').write_text(signature)
 (kit/'product-provenance.json').write_text(json.dumps({'source_sha':SHA,'version':'1.0.0b8','architecture':'arm64','signature':'ad_hoc_only','uvicorn':'0.54.0','executable_sha256':sha(app/'Contents/MacOS/AstroPilot'),'uv_lock_sha256':sha(source/'uv.lock')}),encoding='utf-8')
# Qualify actual Uvicorn startup/graceful shutdown independently of the frozen UI.
runtime=root/'venv-runtime';env['UV_PROJECT_ENVIRONMENT']=str(runtime)
call(['uv','sync','--locked','--extra','test','--python','3.13.5'])
runtime_python=runtime/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
distribution=root/'distribution-tests.xml'
call([str(runtime_python),'-m','pytest','-q',
 'tests/architecture/test_packaging_contract.py',
 'tests/architecture/test_windows_packaging_contract.py',
 'tests/architecture/test_windows_installer_contract.py',
 'tests/architecture/test_windows_candidate_artifacts.py',
 'tests/architecture/test_macos_release_source_identity.py',
 '--junitxml='+str(distribution)])
import xml.etree.ElementTree as ET
checks=ET.parse(distribution)
assert not any(checks.findall('.//'+kind) for kind in ('failure','error'))
skipped=[case for case in checks.findall('.//testcase') if case.find('skipped') is not None]
assert ([case.attrib['name'] for case in skipped]==['test_native_inno_engine_no_output_compile'] if sys.platform=='darwin' else not skipped)
env.update(PRODUCT_SOURCE=str(source),LIFECYCLE_PROOF=str(root/'runtime-proof'))
call([str(runtime_python),str(tools/'runtime_lifecycle.py')],cwd=source)
# Separate locked toolchain: no changes to product dependencies.
venv=root/'venv-controller';call(['uv','venv','--python','3.13.5',str(venv)]);python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
call(['uv','pip','sync','--require-hashes','--python',str(python),str(tools/'requirements.txt')]);call([str(python),'-m','unittest','test_protocol','test_browser_permissions'],cwd=tools)
call([str(python),'-m','PyInstaller','--noconfirm','--clean','--onedir','--console','--name','TestController','--collect-data','tzdata','--distpath',str(root/'controller-dist'),'--workpath',str(root/'controller-build'),'--specpath',str(root/'controller-spec'),str(tools/'controller.py')],cwd=tools)
shutil.copytree(root/'controller-dist/TestController',kit/'TestController',symlinks=True)
if sys.platform=='darwin':
 controller=kit/'TestController/TestController';call(['/usr/bin/codesign','--verify','--deep','--strict',str(controller)])
 signature=subprocess.check_output(['/usr/bin/codesign','-d','--verbose=4',str(controller)],stderr=subprocess.STDOUT,text=True);assert 'Signature=adhoc' in signature and 'TeamIdentifier=not set' in signature;(kit/'controller-signature.txt').write_text(signature)
# Official pinned Chrome; only its per-kit browser profile is used.
sys.path.insert(0,str(source/'scripts/ci/night_chain'));from setup_browser import install
chrome,provenance=install();chrome_root=chrome.parents[3] if sys.platform=='darwin' else chrome.parent
shutil.copytree(chrome_root,kit/'browser',symlinks=True)
browser_rel=(kit/'browser'/chrome.relative_to(chrome_root)).relative_to(kit).as_posix()
(kit/'browser-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
shutil.copy2(tools/'Guide.html',kit/'Guide.html');shutil.copy2(tools/'LIRE-MOI.txt',kit/'LIRE-MOI.txt')
(kit/'kit.json').write_text(json.dumps({'source_sha':SHA,'platform':platform,'browser':browser_rel,'operations_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ops,text=True).strip(),'public_synthetic_only':True}),encoding='utf-8')
audit=kit/'Audit';audit.mkdir()
for p in tools.iterdir():
 if p.is_file():shutil.copy2(p,audit/p.name)
for name in ('LICENSE','LICENSE.txt'):
 if (source/name).is_file():shutil.copy2(source/name,kit/('NightMerit-'+name))
if os.name=='nt':
 for name,arg in [('DEMARRER-TEST.cmd',''),('REPRENDRE-TEST.cmd',' --resume')]:
  (kit/name).write_bytes(('@echo off\r\ncd /d "%~dp0"\r\n"TestController\\TestController.exe"'+arg+'\r\nif errorlevel 1 pause\r\n').encode())
else:
 for name,arg in [('DEMARRER-TEST.command',''),('REPRENDRE-TEST.command',' --resume')]:
  p=kit/name;p.write_text('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\n./TestController/TestController'+arg+'\ncode=$?\nif [ "$code" -ne 0 ]; then printf "Appuyez sur Entree pour fermer. "; read answer; fi\nexit "$code"\n');p.chmod(0o755)
def inventory():
 rows={}
 for base,dirs,files in os.walk(kit,followlinks=False):
  for name in dirs+files:
   p=Path(base)/name;rel=p.relative_to(kit).as_posix()
   if p.is_symlink():rows[rel]={'link':os.readlink(p)}
   elif p.is_file() and rel!='manifest.json':rows[rel]={'sha256':sha(p)}
 return rows
(kit/'manifest.json').write_text(json.dumps({'source_sha':SHA,'files':inventory()},indent=2),encoding='utf-8')
# Validate a physically identical disposable copy; output kit remains pristine.
validation=root/'validation-kit';shutil.copytree(kit,validation,symlinks=True)
env.update(PRODUCT_SOURCE=str(source),KIT_ROOT=str(validation),KIT_PROOF=str(root/'proof'))
call([str(python),str(tools/'selftest.py')],cwd=tools,timeout=600)
# Qualify the exact frozen product in Zurich and Winnipeg, not only the guide.
exe=kit/'candidate'/('AstroPilot.exe' if os.name=='nt' else 'AstroPilot.app/Contents/MacOS/AstroPilot')
env.update(PRODUCT_SOURCE=str(source),APPROVED_SHA=SHA,CANDIDATE_EXE=str(exe),RECOVERY_PROOF=str(root/'packaged-proof'))
call([str(python),str(ops/'tooling/packaged70/qualify.py')],cwd=source,timeout=600)
# Produce a standalone Mac app archive, distinct from the internal guide kit.
if sys.platform=='darwin':
 release=root/'mac-candidate';release.mkdir()
 app=kit/'candidate/AstroPilot.app';identity=json.loads(subprocess.check_output([str(exe),'--runtime-identity'],cwd=root,env=env,text=True))
 assert identity=={'application':'astropilot','architecture':'arm64','build':SHA[:7],'version':'1.0.0b8'},identity
 candidate_archive=release/'AstroPilot-1.0.0-beta.8-macos-arm64.zip'
 call(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',str(app),str(candidate_archive)],cwd=root)
 with zipfile.ZipFile(candidate_archive) as z:assert z.testzip() is None
 original=inventory();restored_app=root/'mac-roundtrip';restored_app.mkdir()
 call(['/usr/bin/ditto','-x','-k',str(candidate_archive),str(restored_app)])
 call(['/usr/bin/codesign','--verify','--deep','--strict',str(restored_app/'AstroPilot.app')])
 def app_inventory(bundle):
  rows={}
  for base,dirs,files in os.walk(bundle,followlinks=False):
   for name in dirs+files:
    p=Path(base)/name;rel=p.relative_to(bundle).as_posix()
    if p.is_symlink():rows[rel]={'link':os.readlink(p)}
    elif p.is_file():rows[rel]={'sha256':sha(p),'size':p.stat().st_size}
  return rows
 assert app_inventory(app)==app_inventory(restored_app/'AstroPilot.app')
 meta=json.loads((kit/'product-provenance.json').read_text());meta.update(runtime_identity=identity,operations_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ops,text=True).strip(),archive={'name':candidate_archive.name,'sha256':sha(candidate_archive),'size':candidate_archive.stat().st_size},bundle_inventory=app_inventory(app),zip_roundtrip_verified=True,public_release=False,notarized=False)
 (release/'provenance.json').write_text(json.dumps(meta,indent=2))
 (release/(candidate_archive.name+'.sha256')).write_text(sha(candidate_archive)+'  '+candidate_archive.name+'\n')
 shutil.copy2(kit/'mac-signature.txt',release/'signature.txt')
 assert inventory()==original

# Validate pristine inventory after all qualification (before distribution ZIP).
assert inventory()==json.loads((kit/'manifest.json').read_text())['files']
for folder in ('COPIES-ISOLEES','RESULTATS'):assert not (kit/folder).exists()
archive=root/(kit.name+'.zip')
if sys.platform=='darwin':call(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',str(kit),str(archive)],cwd=root)
else:
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for p in kit.rglob('*'):
   if p.is_file():z.write(p,p.relative_to(kit.parent))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
roundtrip=root/'roundtrip';roundtrip.mkdir()
if sys.platform=='darwin':call(['/usr/bin/ditto','-x','-k',str(archive),str(roundtrip)],cwd=root)
else:
 with zipfile.ZipFile(archive) as z:z.extractall(roundtrip)
restored=roundtrip/kit.name
call([str(restored/'TestController'/('TestController.exe' if os.name=='nt' else 'TestController')),'--verify-only'],cwd=restored)
if sys.platform=='darwin':call(['/usr/bin/codesign','--verify','--deep','--strict',str(restored/'candidate/AstroPilot.app')])
(root/(archive.name+'.sha256')).write_text(sha(archive)+'  '+archive.name+'\n')
write={'result':'PASS','kit':archive.name,'sha256':sha(archive),'source_sha':SHA,'platform':platform,'pristine':True,'zip_roundtrip_verified':True,'files':len(inventory()),'operations_sha':json.loads((kit/'kit.json').read_text())['operations_sha']};(root/'kit-validation.json').write_text(json.dumps(write,indent=2))
print(json.dumps(write),flush=True)
