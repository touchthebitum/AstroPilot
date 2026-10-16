"""Native frozen runtime qualification; only generated public stores are used."""
from pathlib import Path
import os,sys,json,subprocess,hashlib,platform,zipfile
SOURCE=Path(os.environ['PRODUCT_SOURCE']).resolve();OUT=Path(os.environ['RECOVERY_PROOF']).resolve();SHA=os.environ['APPROVED_SHA'];EXE=Path(os.environ['CANDIDATE_EXE']).resolve()
for key in ('CURRENT_CANDIDATE','LEGACY_CANDIDATE','MODERN_CANDIDATE'):os.environ[key]=str(EXE)
os.environ['MODERN_SHA']=SHA;os.environ['UPGRADE_PROOF']=str(OUT)
import runtime
from weather_fixture import Forecast
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo,reset_tzpath
reset_tzpath(())
sys.path.insert(0,str(SOURCE/'scripts/ci/night_chain'))
from setup_browser import install

def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def browser(case,label,mode,chrome,mission=None):
 proof=case/('ui-'+mode+'-'+label);proof.mkdir()
 env=runtime.environment(case);env.update(CASE_ROOT=str(case),CASE_PROOF=str(proof),PRODUCT_SOURCE=str(SOURCE),NIGHT_CHAIN_URL='http://127.0.0.1:8000',CHROME_BINARY=str(chrome),UI_INTENT='sh2-129_ha' if label=='ha' else 'ou4_oiii',BROWSER_MODE=mode,EXECUTION_ID='public-execution-'+label)
 if mission:env['MISSION_ID']=mission['accepted']['body']['mission_id'];env['EXECUTION_ID']=mission['session']['execution']['execution_id']
 with (proof/'driver.log').open('w',encoding='utf-8') as log:subprocess.run(['node',str(Path(__file__).with_name('browser.cjs'))],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
 result=json.loads((proof/'browser-result.json').read_text(encoding='utf-8'));assert result['result']=='PASS';return result

def credit(case,label,missions):
 rev=runtime.request('GET','/v1/configuration')['profile_revision']
 return runtime.request('POST','/v1/executions/'+missions[label]['session']['execution']['execution_id']+'/intent-progress-credit',{'expected_revision':rev,'evidence_ids':[missions[label]['session']['evidence'][0]['evidence_id']],'confirm_historical_baseline':False})
def check(case,missions):
 p=runtime.request('GET','/v1/projects/Sh2-129/progress');totals={r['acquisition_intent_id']:r['effective_total_seconds'] for r in p['intent_progress_breakdown']};assert totals=={'sh2-129_ha':5400,'ou4_oiii':900},totals
 for label,total in [('ha',5400),('oiii',900)]:
  session=runtime.request('GET','/v1/executions/'+missions[label]['session']['execution']['execution_id']+'/session');assert session['execution']['status']=='completed' and session['acquired_after_seconds']==total,session
  for _ in range(3):assert credit(case,label,missions)['status']=='already_applied'
  a=missions[label]['accepted'];r=runtime.request('POST','/v1/decision-selections',a['request']);assert r['mission_id']==a['body']['mission_id']
 return totals

def time_assets():
 runtime.check_assets()
 with runtime.OPENER.open('http://127.0.0.1:8000/ui/timezone-authority.js') as r:assert r.read()==(SOURCE/'astropilot/web/timezone-authority.js').read_bytes()
 with runtime.OPENER.open('http://127.0.0.1:8000/ui/timezone-data.js') as r:
  raw=r.read();assert r.headers['cache-control']=='no-store'
 data=json.loads(raw.decode().removeprefix('globalThis.NightMeritTimeData=').removesuffix(';'))
 assert data['package_version']=='2026.5' and data['iana_version']=='2026e',data.keys()
 assert data['id']=='c5bc501f192e0894008277cc4b76957a10d37cac092de4f318a7eed0a2c382d5'
 with runtime.OPENER.open('http://127.0.0.1:8000/v1/configuration') as r:assert r.headers['X-NightMerit-Time-Authority']==data['id']
 assert data['zones']['America/Winnipeg']=='6072e5fb802900b193407239b4fb4de9fb2ce80b43ea0f4286a954665b565cbd'
 return {'id':data['id'],'tzdata':data['package_version'],'IANA':data['iana_version'],'asset_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

def main():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==SHA
 OUT.mkdir(parents=True,exist_ok=False)
 chrome,provenance=install();write(OUT/'browser-provenance.json',provenance)
 payload=EXE.parent if os.name=='nt' else EXE.parents[2];inventory=runtime.bundle_inventory(payload);rows=[]
 for name,zone,lat,lon in [('zurich','Europe/Zurich','46.888','6.55'),('winnipeg','America/Winnipeg','49.895','-97.138')]:
  case=OUT/name;case.mkdir();(case/'QUALIFICATION_ONLY').write_text('PUBLIC SYNTHETIC ONLY',encoding='utf-8')
  now=datetime.now(timezone.utc).astimezone(ZoneInfo(zone));day=(now.date()+timedelta(days=1)).isoformat()
  write(case/'fixture.json',{'zone':zone,'night_date':now.date().isoformat(),'availability':{'mode':'fixed_window','start_local':day+'T00:30','end_local':day+'T03:30'}})
  missions={}
  with Forecast(case,zone,lat,lon) as forecast:
   with runtime.Server(EXE,case,SHA,'1.0.0b8') as server:
    r=runtime.request('PUT','/v1/configuration',{'expected_revision':0,'site':{'name':'PUBLIC PACKAGED FIXTURE '+name,'latitude':float(lat),'longitude':float(lon),'bortle':4},'equipment':{'preset_id':'samyang_183'},'projects':{'Sh2-129':{'hours':0,'target_hours':20,'importance':9}}})
    runtime.request('PUT','/v1/projects/Sh2-129/progress',{'expected_revision':r['profile_revision'],'imaging_field_id':'sh2-129_ou4','acquisition_intent_progress':[{'acquisition_intent_id':i,'acquired_duration_manual':0} for i in ('sh2-129_ha','ou4_oiii')],'acquisition_intent_targets':[{'acquisition_intent_id':i,'target_hours':6} for i in ('sh2-129_ha','ou4_oiii')]})
    assets=time_assets();config=runtime.request('GET','/v1/configuration');assert config['site']['timezone']==zone,config
    dst=[]
    if name=='zurich':
     for start,end,code in [('2026-03-29T02:30','2026-03-29T03:30','session_availability_local_time_nonexistent'),('2026-10-25T02:30','2026-10-25T03:30','session_availability_local_time_ambiguous')]:
      r=runtime.request('POST','/v1/tonight',{'availability':{'mode':'fixed_window','start_local':start,'end_local':end}},expected=422);assert r['detail']['code']==code,r;dst.append(r)
    if name=='winnipeg':
     # The zero duration is intentionally invalid AFTER unique local time normalization.
     # Old rules refuse 01:30 as ambiguous before reaching duration validation.
     r=runtime.request('POST','/v1/tonight',{'availability':{'mode':'start_and_duration','start_local':'2026-11-01T01:30','duration':0}},expected=422)
     assert r['detail']['code']=='session_availability_duration_must_be_positive',r;dst.append({'unique_0130_confirmed_by_later_duration_validation':r})
    for label,seconds in [('ha',5400),('oiii',900)]:
     missions[label]=browser(case,label,'accept',chrome)
    totals=check(case,missions);identity=server.identity
   baseline=runtime.authority(case/'data');write(case/'authority-before-restart.json',baseline)
   for boot in range(2):
    with runtime.Server(EXE,case,SHA,'1.0.0b8'):
     assert time_assets()==assets;check(case,missions)
     if boot==0:
      for label in ('ha','oiii'):browser(case,label,'reopen',chrome,missions[label])
    assert runtime.authority(case/'data')==baseline,('Restart/replay changed canonical bytes',name,boot)
   assert len(forecast.rows)==2 and all('error' not in r for r in forecast.rows),forecast.rows
  assert not (case/'data/user_filters.json').exists()
  rows.append({'site':name,'timezone':zone,'result':'PASS','identity':identity,'authority':assets,'dst_refusals':dst,'totals':totals,'restarts':2,'credit_replays':18,'canonical_bytes_unchanged':True,'no_legacy_inventory':True})
  write(OUT/'partial-result.json',rows)
 assert runtime.bundle_inventory(payload)==inventory,'Packaged payload mutated'
 write(OUT/'result.json',{'result':'PASS','sha':SHA,'platform':platform.platform(),'native_frozen_runtime':True,'user_data_used':False,'weather':'loopback TLS fixture returns coherent synthetic Open-Meteo payload; actual frozen requests/ingress/scoring/decision endpoints run unchanged, TLS verification enabled via process-only temporary CA','ui':'real DOM confirmation, session start, closure, evidence, credit and persisted credit reopening; real Tonight decision generation; no UI/API response replacement or view model injection','closure_and_credit':'real DOM actions POST to unmodified frozen HTTP API; browser start clock set two hours back and restored before closure, server clock unchanged','rows':rows,'payload_unchanged':True})
 print('PASS frozen Windows/Mac timezone authority, DOM Ha/OIII confirmation, closure, credit, two restarts and replay')
if __name__=='__main__':main()
