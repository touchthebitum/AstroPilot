"""PUBLIC CI fixture only: establish the already-credited source before testing resume."""
import os,sys,json,pathlib,subprocess,zipfile,hashlib,time,urllib.request,shutil,datetime
base=pathlib.Path(os.environ['RUNNER_TEMP'])/'source-fixture';base.mkdir();source=base/'essai-isole-20261015-151443-f27734';source.mkdir()
seed=base/'seed';seed.mkdir();(seed/'QUALIFICATION_ONLY').write_text('Public CI only');data=seed/'data';data.mkdir()
helper=pathlib.Path(__file__).parents[1]/'packaged/session_seed.py'
subprocess.run([sys.executable,str(helper),'--worker',str(data),json.dumps({'method':'INIT'})],check=True,timeout=120)
shutil.move(str(data),str(source/'ASTROPILOT_DATA_DIR'));data=source/'ASTROPILOT_DATA_DIR'
artifacts=pathlib.Path(os.environ['RUNNER_TEMP'])/'official-kit-artifacts';p=json.loads((artifacts/'provenance.json').read_text());assert p['source_sha']=='0dcde494c8450176f445cc29b28d004eddb60734'
name='AstroPilot-1.0.0b8-windows-x86_64-portable.zip';assert hashlib.sha256((artifacts/name).read_bytes()).hexdigest()==p['artifacts'][name]['sha256']
with zipfile.ZipFile(artifacts/name) as z:z.extractall(source/'runtime')
env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_'))}
for k in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR','XDG_CACHE_HOME'):
 path=base/k;path.mkdir();env[k]=str(path)
env['ASTROPILOT_DATA_DIR']=str(data);noop=base/'noop.py';noop.write_text('pass');env['BROWSER']=f'"{sys.executable}" "{noop}" %s'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def req(method,path,body=None):
 q=urllib.request.Request('http://127.0.0.1:8000'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
 with opener.open(q,timeout=15) as r:return json.load(r)
child=subprocess.Popen([str(source/'runtime/AstroPilot/AstroPilot.exe')],env=env,stdout=(base/'seed-stdout.log').open('w'),stderr=(base/'seed-stderr.log').open('w'))
try:
 for _ in range(120):
  try:
   assert req('GET','/v1/runtime-identity')['build']=='0dcde49';break
  except OSError:time.sleep(.5)
 else:raise AssertionError('Source fixture startup failed')
 for label,seconds in [('ha',1800),('oiii',900)]:
  eid='packaged-ui-'+label;mid='qualification-mission-'+label;evidence='resume-evidence-'+label
  req('POST','/v1/executions',{'execution_id':eid,'mission_id':mid})
  start=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=1);end=start+datetime.timedelta(hours=1)
  body={'execution_id':eid,'mission_id':mid,'status':'in_progress','actual_start':start.isoformat(),'actual_end':None,'actual_duration':None};req('POST','/v1/execution-transitions',body)
  body.update(status='completed',actual_end=end.isoformat(),actual_duration=3600);req('POST','/v1/execution-transitions',body)
  req('POST','/v1/outcome-evidence',{'evidence_id':evidence,'execution_id':eid,'category':'acquisition','observed_at':end.isoformat(),'source':'user','usable_integration_duration':seconds})
  assert req('POST','/v1/executions/'+eid+'/intent-progress-credit',{'expected_revision':json.loads((data/'user_profile.json').read_text())['profile_revision'],'evidence_ids':[evidence],'confirm_historical_baseline':label=='ha'})['status']=='applied'
finally:
 child.terminate();child.wait(timeout=30)
print('PUBLIC source fixture ready; setup creation is separate from resume operations')
