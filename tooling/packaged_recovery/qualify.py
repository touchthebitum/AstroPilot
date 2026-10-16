"""Qualify actual frozen candidates, exclusively on disposable public data."""
from pathlib import Path
import os,sys,json,subprocess,shutil,hashlib,platform
SOURCE=Path(os.environ['PRODUCT_SOURCE']).resolve()
OUT=Path(os.environ['RECOVERY_PROOF']).resolve()
SHA=os.environ['APPROVED_SHA']
EXE=Path(os.environ['CANDIDATE_EXE']).resolve()
# Reuse ownership-checked packaged launcher, isolated environment and exact asset verifier.
for key in ('CURRENT_CANDIDATE','LEGACY_CANDIDATE','MODERN_CANDIDATE'):
 os.environ[key]=str(EXE)
os.environ['MODERN_SHA']=SHA;os.environ['UPGRADE_PROOF']=str(OUT)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'upgrade'))
import qualify as runtime
sys.path.insert(0,str(SOURCE/'scripts/ci/night_chain'))
from setup_browser import install

def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
def credit(case,label):
 rev=json.loads((case/'data/user_profile.json').read_text(encoding='utf-8'))['profile_revision']
 return runtime.request('POST','/v1/executions/recovery-execution-'+label+'/intent-progress-credit',{'expected_revision':rev,'evidence_ids':['recovery-evidence-'+label],'confirm_historical_baseline':label=='ha'})
def check(case):
 p=runtime.request('GET','/v1/projects/Sh2-129/progress')
 totals={x['acquisition_intent_id']:x['effective_total_seconds'] for x in p['intent_progress_breakdown']}
 assert totals=={'sh2-129_ha':5400,'ou4_oiii':900},totals
 for label,total in [('ha',5400),('oiii',900)]:
  assert runtime.request('GET','/v1/executions/recovery-execution-'+label+'/session')['acquired_after_seconds']==total
  for _ in range(3):assert credit(case,label)['status']=='already_applied'
 return totals

def main():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==SHA
 OUT.mkdir(parents=True,exist_ok=False)
 chrome,provenance=install();write(OUT/'browser-provenance.json',provenance)
 healthy=OUT/'healthy';healthy.mkdir();(healthy/'QUALIFICATION_ONLY').write_text('PUBLIC SYNTHETIC ONLY',encoding='utf-8')
 env=runtime.environment(healthy);env['CASE_ROOT']=str(healthy);env['PRODUCT_SOURCE']=str(SOURCE);env['PYTHONUTF8']='1'
 subprocess.run([sys.executable,str(Path(__file__).with_name('seed.py'))],env=env,check=True,timeout=180,cwd=SOURCE)
 missions=json.loads((healthy/'missions.json').read_text(encoding='utf-8'))
 with runtime.Server(EXE,healthy,SHA,'1.0.0b8'):
  runtime.check_assets()
  for label,seconds in [('ha',1800),('oiii',900)]:
   mid=missions[label]['mission_id'];eid='recovery-execution-'+label
   runtime.request('POST','/v1/executions',{'execution_id':eid,'mission_id':mid})
   b={'execution_id':eid,'mission_id':mid,'status':'in_progress','actual_start':'2026-10-15T22:30:00+00:00','actual_end':None,'actual_duration':None}
   runtime.request('POST','/v1/execution-transitions',b)
   b.update(status='completed',actual_end='2026-10-15T23:30:00+00:00',actual_duration=3600)
   runtime.request('POST','/v1/execution-transitions',b)
   runtime.request('POST','/v1/outcome-evidence',{'evidence_id':'recovery-evidence-'+label,'execution_id':eid,'category':'acquisition','observed_at':'2026-10-15T23:30:00+00:00','source':'user','usable_integration_duration':seconds})
   assert credit(healthy,label)['status']=='applied'
  check(healthy)
 frozen=OUT/'frozen';shutil.copytree(healthy/'data',frozen)
 baseline=runtime.authority(frozen);profile=(frozen/'user_profile.json').read_bytes()
 rows=[]
 for name,bad in [('invalid_utf8',b'\xff'),('deep_json',b'['*10000+b']'*10000),('huge_integer',b'{"x":'+b'9'*10000+b'}')]:
  case=OUT/name;case.mkdir();(case/'QUALIFICATION_ONLY').write_text('PUBLIC FAULT COPY',encoding='utf-8');shutil.copytree(frozen,case/'data')
  active=case/'data/user_profile.json';active.write_bytes(bad)
  with runtime.Server(EXE,case,SHA,'1.0.0b8') as server:
   refused=runtime.request('GET','/v1/configuration',expected=503);assert refused['detail']['code']=='configuration_corrupt',refused
   assert active.read_bytes()==bad and not list((case/'data').glob('.user_profile.corrupt.*.json'))
   env=runtime.environment(case);env.update(CASE_ROOT=str(case),CASE_PROOF=str(case),PRODUCT_SOURCE=str(SOURCE),NIGHT_CHAIN_URL='http://127.0.0.1:8000',CHROME_BINARY=str(chrome),PYTHONUTF8='1')
   with (case/'browser-driver.log').open('w',encoding='utf-8') as log:
    subprocess.run([os.environ.get('NODE_BINARY','node'),str(Path(__file__).with_name('browser.cjs'))],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=175,check=True)
   browser=json.loads((case/'browser-result.json').read_text(encoding='utf-8'));assert browser['result']=='PASS'
   quarantine=list((case/'data').glob('.user_profile.corrupt.*.json'));assert len(quarantine)==1 and quarantine[0].read_bytes()==bad
   assert not active.exists()
   assert runtime.request('POST','/v1/configuration/recover')['configured'] is False
   assert len(list((case/'data').glob('.user_profile.corrupt.*.json')))==1
   identity=server.identity
  # Restore only the healthy profile, with server stopped; never regenerate canonical stores.
  other_before={k:v for k,v in runtime.authority(case/'data').items() if k!='user_profile.json' and not k.startswith('.user_profile.corrupt.')}
  assert other_before=={k:v for k,v in baseline.items() if k!='user_profile.json'},'Recovery changed canonical authority'
  active.write_bytes(profile)
  for boot in range(2):
   with runtime.Server(EXE,case,SHA,'1.0.0b8'):
    assert runtime.request('GET','/v1/configuration')['configured'] is True
    totals=check(case)
    conflict=runtime.request('POST','/v1/configuration/recover',expected=409);assert conflict['detail']['code']=='configuration_recovery_conflict'
   actual={k:v for k,v in runtime.authority(case/'data').items() if not k.startswith('.user_profile.corrupt.')}
   assert actual==baseline,('Restoration/replay changed authority',name,actual,baseline)
   assert quarantine[0].read_bytes()==bad
  rows.append({'case':name,'result':'PASS','identity':identity,'ui_recovery':browser,'quarantine_sha256':hashlib.sha256(bad).hexdigest(),'restored_profile_sha256':hashlib.sha256(profile).hexdigest(),'totals':totals,'restarts':2,'credit_replays':12,'healthy_recovery_refused':True,'canonical_authority_unchanged':True})
 assert runtime.authority(frozen)==baseline
 write(OUT/'result.json',{'result':'PASS','sha':SHA,'platform':platform.platform(),'real_packaged_runtime':True,'real_browser_recovery':True,'fixture_decisions_via_production_api':True,'credits_created_by_packaged_runtime':True,'restoration':'controlled healthy snapshot; not automatic UI backup restore','user_data_used':False,'authority_sha256':baseline,'rows':rows})
 print('PASS actual packaged profile recovery, restoration, two restarts and idempotent replay')
if __name__=='__main__':main()
