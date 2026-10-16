"""Contract failures only: all non-Git tools and signing identities are simulated."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util,json,os,subprocess,sys,zipfile
import pytest

SOURCE=Path(os.environ['PRODUCT_SOURCE'])

def load():
 spec=importlib.util.spec_from_file_location('release_gate_audit',SOURCE/'scripts/release_macos.py')
 m=importlib.util.module_from_spec(spec);sys.path.insert(0,str(SOURCE/'scripts'))
 try:spec.loader.exec_module(m)
 finally:sys.path.pop(0)
 return m

@pytest.mark.parametrize('fault', ['bundle_verify','bundle_display','notary_command','notary_rejected','notary_invalid_json','notary_no_id','staple','bundle_ticket','bundle_gatekeeper','zip','extracted_verify','extracted_ticket','extracted_gatekeeper','checksum'])
def test_distribution_failure_never_emits_checksum_sidecar(tmp_path,fault):
 m=load();app=tmp_path/'dist/AstroPilot.app';artifact=tmp_path/'dist/AstroPilot-1.0.0-beta.8-macos-arm64.zip';side=artifact.with_suffix('.zip.sha256');calls=[]
 (tmp_path/'pyproject.toml').write_text('[project]\nversion="1.0.0b8"\n',encoding='utf-8')
 def build(**kwargs):app.mkdir(parents=True);return app
 def runner(command,**kwargs):
  calls.append(command);stage=None
  if command[:2]==['git','rev-parse']:return SimpleNamespace(stdout='a'*40)
  if command[:2]==['git','status']:return SimpleNamespace(stdout='')
  if command[0]=='codesign':stage=('bundle_' if command[-1]==str(app) else 'extracted_')+('verify' if command[1]=='--verify' else 'display')
  elif command[:3]==['xcrun','notarytool','submit']:
   if fault=='notary_rejected':return SimpleNamespace(stdout='{"status":"Invalid","id":"public"}')
   if fault=='notary_invalid_json':return SimpleNamespace(stdout='{')
   if fault=='notary_no_id':return SimpleNamespace(stdout='{"status":"Accepted"}')
   stage='notary_command'
  elif command[:2]==['xcrun','stapler']:stage='staple' if command[2]=='staple' else ('bundle_ticket' if command[-1]==str(app) else 'extracted_ticket')
  elif command[0]=='spctl':stage='bundle_gatekeeper' if command[-1]==str(app) else 'extracted_gatekeeper'
  elif command[:5]==['ditto','-c','-k','--norsrc','--keepParent']:stage='zip'
  elif command[:3]==['shasum','-a','256']:stage='checksum'
  if stage==fault:
   if fault=='checksum':return SimpleNamespace(stdout='invalid_digest')
   raise subprocess.CalledProcessError(1,command)
  if command[:4]==['ditto','-c','-k','--keepParent']:Path(command[-1]).touch()
  if stage=='zip':
   with zipfile.ZipFile(command[-1],'w') as z:z.writestr('AstroPilot.app/Contents/Info.plist','public fixture')
  if command[:3]==['ditto','-x','-k']:(Path(command[-1])/'AstroPilot.app').mkdir()
  if stage=='notary_command':return SimpleNamespace(stdout='{"status":"Accepted","id":"public-fixture"}')
  return SimpleNamespace(stdout='')
 with pytest.raises((RuntimeError,ValueError,subprocess.CalledProcessError)):
  m.release(root=tmp_path,codesign_identity='SIMULATED ONLY',notary_profile='SIMULATED ONLY',build_function=build,runner=runner)
 assert not side.exists()
 if fault!='checksum':assert not any(c[:3]==['shasum','-a','256'] for c in calls)
