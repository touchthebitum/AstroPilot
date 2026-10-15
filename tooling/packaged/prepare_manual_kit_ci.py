"""Prepare PUBLIC synthetic equivalent of the private manual kit, never private data."""
import pathlib,os,subprocess,json,hashlib,shutil,zipfile,sys
source=pathlib.Path(os.environ['PRODUCT_SOURCE']);base=pathlib.Path(os.environ['RUNNER_TEMP'])/'manual-kit-native';base.mkdir();(base/'QUALIFICATION_ONLY').write_text('public synthetic qualification')
data=base/'data';data.mkdir()
subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('session_seed.py')),'--worker',str(data),json.dumps({'method':'INIT'})],check=True,timeout=120)
kit=pathlib.Path(os.environ['KIT_TEST_ROOT']);kit.mkdir()
shutil.copy2(pathlib.Path(__file__).with_name('manual_kit.ps1'),kit/'Lancer-qualification.ps1')
artifacts=pathlib.Path(os.environ['RUNNER_TEMP'])/'official-kit-artifacts'
p=json.loads((artifacts/'provenance.json').read_text());assert p['source_sha']=='0dcde494c8450176f445cc29b28d004eddb60734'
portable='AstroPilot-1.0.0b8-windows-x86_64-portable.zip';assert hashlib.sha256((artifacts/portable).read_bytes()).hexdigest()==p['artifacts'][portable]['sha256'];shutil.copy2(artifacts/portable,kit/portable)
with zipfile.ZipFile(kit/'Profil-Mac-test.zip','x',zipfile.ZIP_DEFLATED) as z:
 for f in data.rglob('*'):
  if f.is_file() and not f.name.startswith('.') and f.suffix=='.json':z.write(f,f.relative_to(data).as_posix())
manifest={'files':[{'path':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in kit.iterdir() if f.is_file()]}
(kit/'Manifest-kit.json').write_text(json.dumps(manifest),encoding='utf-8')
