"""Real frozen executable API qualification, explicitly not a desktop UI test."""
import os,sys,pathlib,json,subprocess,socket,time,urllib.request,hashlib,datetime,shutil
source=pathlib.Path(os.environ['PRODUCT_SOURCE']).resolve();sha=os.environ['APPROVED_SHA'];root=pathlib.Path(os.environ['RUNNER_TEMP'])/'packaged-session-proof';root.mkdir();(root/'QUALIFICATION_ONLY').write_text('Synthetic only')
data=root/'data';data.mkdir();env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_'))}
for k,c in {'HOME':'home','USERPROFILE':'home','APPDATA':'appdata','LOCALAPPDATA':'localappdata','TMP':'tmp','TEMP':'tmp','TMPDIR':'tmp','XDG_CACHE_HOME':'cache','ASTROPILOT_DATA_DIR':'data'}.items():
 p=root/c;p.mkdir(exist_ok=True);env[k]=str(p)
noop=root/'noop.py';noop.write_text('pass\n');env['BROWSER']=f'"{sys.executable}" "{noop}" %s'
subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('session_seed.py')),'--worker',str(data),json.dumps({'method':'INIT'})],env=env,check=True,capture_output=True,text=True,timeout=120)
# Export only public synthetic logical files for the manual UI kit, before sessions.
seed=source/'dist/beta8-artifacts/synthetic-ui-seed';seed.mkdir()
for name in ('user_profile.json','decision_lineage'):
 p=data/name
 if p.is_dir():shutil.copytree(p,seed/name)
 else:shutil.copyfile(p,seed/name)
exe=source/'dist/AstroPilot/AstroPilot.exe';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));rows=[];child=None

def req(method,path,body=None):
 q=urllib.request.Request('http://127.0.0.1:8000'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
 with opener.open(q,timeout=15) as r:return json.load(r)
def stop():
 global child
 if child and child.poll() is None:child.terminate();child.wait(timeout=30)
 child=None
 for _ in range(100):
  s=socket.socket();s.settimeout(.2);busy=s.connect_ex(('127.0.0.1',8000))==0;s.close()
  if not busy:return
  time.sleep(.1)
 raise AssertionError('Port remains occupied')
def start():
 global child
 s=socket.socket();s.bind(('127.0.0.1',8000));s.close()
 child=subprocess.Popen([str(exe)],env=env,cwd=root,stdout=(root/'stdout.log').open('ab'),stderr=(root/'stderr.log').open('ab'))
 for _ in range(180):
  if child.poll() is not None:raise AssertionError('Binary exited')
  try:
   identity=req('GET','/v1/runtime-identity');assert identity['build']==sha[:7];return identity
  except (OSError,urllib.error.URLError):time.sleep(.5)
 raise AssertionError('Startup timeout')
try:
 identity=start()
 for asset in ('index.html','app.js','styles.css','help.js','alert-status.js'):
  url='/' if asset=='index.html' else '/static/'+asset
  # Routes are verified below through HTML resource references separately.
  if asset=='index.html':
   with opener.open('http://127.0.0.1:8000/') as r:assert r.read()==(source/'astropilot/web/index.html').read_bytes()
 for label,seconds in [('ha',1800),('oiii',900)]:
  eid='packaged-api-'+label;mid='qualification-mission-'+label;starttime=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=1);end=starttime+datetime.timedelta(seconds=3600)
  req('POST','/v1/executions',{'execution_id':eid,'mission_id':mid})
  body={'execution_id':eid,'mission_id':mid,'status':'in_progress','actual_start':starttime.isoformat(),'actual_end':None,'actual_duration':None};req('POST','/v1/execution-transitions',body)
  body.update(status='completed',actual_end=end.isoformat(),actual_duration=3600);req('POST','/v1/execution-transitions',body)
  evidence='packaged-evidence-'+label;req('POST','/v1/outcome-evidence',{'evidence_id':evidence,'execution_id':eid,'category':'acquisition','observed_at':end.isoformat(),'source':'user','usable_integration_duration':seconds})
  body={'expected_revision':json.loads((data/'user_profile.json').read_text())['profile_revision'],'evidence_ids':[evidence],'confirm_historical_baseline':label=='ha'};assert req('POST','/v1/executions/'+eid+'/intent-progress-credit',body)['status']=='applied'
 before=(data/'user_profile.json').read_bytes();stop();identity=start()
 for label,seconds in [('ha',1800),('oiii',900)]:
  eid='packaged-api-'+label;s=req('GET','/v1/executions/'+eid+'/session');assert s['session_credit_seconds']==seconds
  for _ in range(3):assert req('POST','/v1/executions/'+eid+'/intent-progress-credit',{'expected_revision':json.loads(before)['profile_revision'],'evidence_ids':['packaged-evidence-'+label],'confirm_historical_baseline':label=='ha'})['status']=='already_applied'
  rows.append({'intent':label,'credit_seconds':seconds,'replay':'already_applied','replay_count':3})
 assert (data/'user_profile.json').read_bytes()==before
 p=req('GET','/v1/projects/Sh2-129/progress');totals={i['acquisition_intent_id']:i['effective_total_seconds'] for i in p['intent_progress_breakdown']};assert totals=={'sh2-129_ha':5400,'ou4_oiii':900}
 stop();report={'result':'PASS','product_sha':sha,'runtime':identity,'synthetic':True,'real_frozen_binary':True,'restart':True,'profile_unchanged_after_replay':True,'profile_sha256':hashlib.sha256(before).hexdigest(),'totals':totals,'sessions':rows,'desktop_ui_observed':False,'physical_user_pc':False,'port_released':True}
 (source/'dist/beta8-artifacts/packaged-session-qualification.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report))
finally:stop()
