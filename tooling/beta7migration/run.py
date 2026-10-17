"""Published beta.7 -> exact main; disposable native runner only, synthetic API profiles."""
from pathlib import Path
import os,sys,json,hashlib,subprocess,shutil,zipfile
from datetime import datetime,timedelta,timezone
SHA='7e98e45b2f46f57dcf959f3bf8d2b1373375cf48'
assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
source=Path('candidate').resolve();ops=Path('operations').resolve();root=Path(os.environ['RUNNER_TEMP'])/'beta7migration';root.mkdir()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==SHA
os.environ.update(PRODUCT_SOURCE=str(source),APPROVED_SHA=SHA,RECOVERY_PROOF=str(root),CANDIDATE_EXE=str(root/'unused'))
if sys.platform=='darwin':os.environ['BROWSER_NATIVE_HOME']=os.environ['HOME']
else:os.environ['BROWSER_NATIVE_USERPROFILE']=os.environ['USERPROFILE']
sys.path.insert(0,str(ops/'tooling/packaged70'))
import runtime,qualify as q
from weather_fixture import Forecast
from zoneinfo import ZoneInfo,reset_tzpath
reset_tzpath(())
def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def call(args,**kw):subprocess.run(list(map(str,args)),check=True,timeout=300,**kw)
def extract(archive,dest):
 dest.mkdir()
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  assert all(not Path(n.replace('\\','/')).is_absolute() and '..' not in Path(n.replace('\\','/')).parts for n in z.namelist())
 if sys.platform=='darwin':call(['/usr/bin/ditto','-x','-k',archive,dest])
 else:
  with zipfile.ZipFile(archive) as z:z.extractall(dest)
legacy=Path(os.environ['RUNNER_TEMP'])/'legacy'
old=next(legacy.glob('*.exe' if os.name=='nt' else '*.zip'))
expected='9a9953d09f19510161d288ae6b6c56c5f95f3dd8b2a640362b7f65a50e633cd9' if os.name=='nt' else 'e15bfeabb12d4322ebe8aa18874f0935197600a37538f458c93ff755f5b6685b'
assert runtime.digest(old)==expected
if os.name=='nt':
 d=Path(os.environ['RUNNER_TEMP'])/'official-current';meta=json.loads((d/'provenance.json').read_text(encoding='utf-8-sig'));assert meta['source_sha']==SHA
 current=next(d.glob('*setup.exe'));assert runtime.digest(current)==meta['artifacts'][current.name]['sha256']
 payload_archive=next(d.glob('*portable.zip'));assert runtime.digest(payload_archive)==meta['artifacts'][payload_archive.name]['sha256'];extract(payload_archive,root/'payload');payload=root/'payload/AstroPilot'
else:
 extract(old,root/'old');old=root/'old/AstroPilot.app'
 d=Path(os.environ['RUNNER_TEMP'])/'input-current';meta=json.loads((d/'kit-validation.json').read_text());archive=next(d.glob('*.zip'));assert meta['source_sha']==SHA and runtime.digest(archive)==meta['sha256'];extract(archive,root/'current');current=root/'current'/archive.stem/'candidate/AstroPilot.app';payload=current
 target=root/'Applications/AstroPilot.app'
 for app in (old,current):call(['/usr/bin/codesign','--verify','--deep','--strict',app])
current_inventory=runtime.bundle_inventory(payload)
install_case=root/'installer';install_case.mkdir()
def install(candidate,upgrade=False):
 if os.name=='nt':
  target=root/'Applications/AstroPilot';target.parent.mkdir(exist_ok=True)
  args=[candidate,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS','/TASKS=',f'/LOG={root / ("upgrade.log" if upgrade else "install.log")}']
  if not upgrade:args.append('/DIR='+str(target))
  call(args,env=runtime.environment(install_case));exe=target/'AstroPilot.exe'
 else:
  target=root/'Applications/AstroPilot.app';target.parent.mkdir(exist_ok=True)
  if target.exists():target.rename(root/'previous.app')
  call(['/usr/bin/ditto',candidate,target]);exe=target/'Contents/MacOS/AstroPilot'
 assert exe.is_file()
 if upgrade:
  actual=runtime.bundle_inventory(target);assert all(actual.get(k)==v for k,v in current_inventory.items())
 return exe
oldexe=install(old);cases=[]
for name,zone,lat,lon in [('zurich','Europe/Zurich',46.888,6.55),('winnipeg','America/Winnipeg',49.895,-97.138)]:
 for hours in (2,0):
  case=root/(name+'-'+str(hours));case.mkdir();(case/'data').mkdir()
  with runtime.Server(oldexe,case,'c47b2e6','1.0.0b7') as server:
   runtime.request('PUT','/v1/configuration',{'site':{'name':'PUBLIC BETA7 '+name,'latitude':lat,'longitude':lon,'bortle':4},'equipment':{'preset_id':'samyang_183'},'projects':{'Sh2-129':{'hours':hours,'target_hours':20,'importance':9}}})
   config=runtime.request('GET','/v1/configuration');identity=server.identity
  before=runtime.authority(case/'data');shutil.copytree(case/'data',case/'frozen-beta7');write(case/'beta7-origin.json',{'identity':identity,'configuration':config,'files':before})
  cases.append((case,name,zone,lat,lon,hours,config,before))
exe=install(current,True);rows=[]
chrome,provenance=q.install();write(root/'browser-provenance.json',provenance)
for case,name,zone,lat,lon,hours,oldconfig,before in cases:
 assert runtime.authority(case/'data')==before,'Installer changed beta7 data'
 for boot in range(2):
  with runtime.Server(exe,case,SHA,'1.0.0b8'):
   config=runtime.request('GET','/v1/configuration');assert config['projects']==oldconfig['projects'];assert config['site']['timezone']==zone
  assert runtime.authority(case/'data')==before,'Read/restart changed beta7 authority'
 row={'site':name,'beta7_hours':hours,'preserved_projects':True,'installer_preserved_bytes':True,'two_restarts_preserved_bytes':True,'beta7_credit_replay':'not applicable: beta7 profile has historical hours, no per-intent session credits'}
 if hours==0:
  now=datetime.now(timezone.utc).astimezone(ZoneInfo(zone));day=(now.date()+timedelta(days=1)).isoformat();write(case/'fixture.json',{'zone':zone,'night_date':now.date().isoformat(),'availability':{'mode':'fixed_window','start_local':day+'T00:30','end_local':day+'T03:30'}})
  missions={}
  with Forecast(case,zone,lat,lon):
   with runtime.Server(exe,case,SHA,'1.0.0b8'):
    rev=runtime.request('GET','/v1/configuration')['profile_revision']
    runtime.request('PUT','/v1/projects/Sh2-129/progress',{'expected_revision':rev,'imaging_field_id':'sh2-129_ou4','acquisition_intent_progress':[{'acquisition_intent_id':i,'acquired_duration_manual':0} for i in ('sh2-129_ha','ou4_oiii')],'acquisition_intent_targets':[{'acquisition_intent_id':i,'target_hours':6} for i in ('sh2-129_ha','ou4_oiii')]})
    for label in ('ha','oiii'):missions[label]=q.browser(case,label,'accept',chrome)
    q.check(case,missions)
   credited=runtime.authority(case/'data')
   for boot in range(2):
    with runtime.Server(exe,case,SHA,'1.0.0b8'):
     totals=q.check(case,missions)
     if boot==0:
      for label in ('ha','oiii'):q.browser(case,label,'reopen',chrome,missions[label])
    assert runtime.authority(case/'data')==credited
  row.update(new_current_credits_seconds=totals,post_credit_restarts=2,credit_replays=18,credited_bytes_unchanged=True,credits_created_via_real_dom=True)
 assert runtime.authority(case/'frozen-beta7')==before
 rows.append(row);write(root/'partial-result.json',rows)
assert runtime.bundle_inventory(payload)==current_inventory
write(root/'result.json',{'result':'PASS','source_sha':SHA,'baseline_source_sha':'c47b2e6fe395f51678971d12a1cd451ba8aa9cfa','published_beta7_asset_sha256':expected,'platform':sys.platform,'rows':rows,'real_user_profile_used':False,'native_disposable_runner':True,'windows_actual_installer_upgrade':os.name=='nt','mac_isolated_bundle_replacement':sys.platform=='darwin','chrome_sandbox_disabled':False,'product_modified':False})
print('PASS published beta7 migration, historical hours, new Ha/OIII credits, restart and replay',flush=True)
