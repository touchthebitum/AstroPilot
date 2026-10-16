"""Native frozen-controller + actual guide DOM + actual candidate DOM + resume test."""
from pathlib import Path
import os,sys,subprocess,json,time,urllib.request,urllib.error,zipfile,hashlib,socket
KIT=Path(os.environ['KIT_ROOT']);OUT=Path(os.environ['KIT_PROOF']);OUT.mkdir()
TOOLS=Path(__file__).parent;SOURCE=Path(os.environ['PRODUCT_SOURCE']);EXE=KIT/'TestController'/('TestController.exe' if os.name=='nt' else 'TestController')
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def wait(fn,label,seconds=150):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  value=fn()
  if value:return value
  time.sleep(.25)
 raise AssertionError('Timeout '+label)
def query(url,path,body=None,token=None):
 req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'X-Kit-Token':token} if token else {})})
 with OPENER.open(req,timeout=100) as r:return json.load(r)
def hashes(case):return {p.relative_to(case/'data').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (case/'data').rglob('*.json') if p.relative_to(case/'data').parts[0]!='Logs'}
def start(resume=False):
 log=(OUT/('resume.log' if resume else 'controller.log')).open('wb');env=os.environ.copy();env['ASTROPILOT_DATA_DIR']=str(OUT/'forbidden');env['ASTROPILOT_GUARDIAN_ATTESTATION_PATH']=str(OUT/'forbidden/attestation.json')
 old_token=None
 if resume and (KIT/'derniere-copie.json').exists():
  old_case=Path(read(KIT/'derniere-copie.json')['path']);old_token=read(old_case/'guide-location.json')['token']
 child=subprocess.Popen([str(EXE),'--laboratory']+(['--resume'] if resume else []),cwd=KIT,env=env,stdout=log,stderr=log)
 case=Path(wait(lambda:read(KIT/'derniere-copie.json')['path'] if (KIT/'derniere-copie.json').exists() else None,'copy'))
 location=wait(lambda:(lambda x:x if x['token']!=old_token else None)(read(case/'guide-location.json')) if (case/'guide-location.json').exists() else None,'guide location')
 return child,case,location,log
forbidden=OUT/'forbidden';forbidden.mkdir();(forbidden/'user_profile.json').write_bytes(b'EXTERNAL SENTINEL - DO NOT TOUCH');before=(forbidden/'user_profile.json').read_bytes()
child=None;guide=None;case=None
try:
 child,case,location,log=start();url=location['url'];token=location['token']
 # Browser-side helpers use isolated HOME and preserve native HOME only for macOS framework services.
 env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
 for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME'):
  p=OUT/'browser-environment'/key;p.mkdir(parents=True);env[key]=str(p)
 env['PRODUCT_SOURCE']=str(SOURCE);env['CHROME_BINARY']=str(KIT/read(KIT/'kit.json')['browser']);env['CASE_ROOT']=str(case);env['CASE_PROOF']=str(OUT);env['NIGHT_CHAIN_URL']=url;env['UI_INTENT']='sh2-129_ha'
 glog=(OUT/'guide-driver.log').open('w',encoding='utf-8');guide=subprocess.Popen(['node',str(TOOLS/'guide_test.cjs')],env=env,stdout=glog,stderr=subprocess.STDOUT)
 state=wait(lambda:read(OUT/'guide-ready.json') if (OUT/'guide-ready.json').exists() else None,'guide real start');write(case/'fixture.json',{'zone':'Europe/Zurich','night_date':state['night_date'],'availability':state['availability']})
 # Browser harness executes the real candidate UI, not a source app.
 records={}
 for label,intent in [('ha','sh2-129_ha'),('oiii','ou4_oiii')]:
  proof=case/('ui-accept-'+label);proof.mkdir();env.update(CASE_PROOF=str(proof),NIGHT_CHAIN_URL='http://127.0.0.1:8000',UI_INTENT=intent,BROWSER_MODE='accept')
  with (proof/'driver.log').open('w',encoding='utf-8') as f:subprocess.run(['node',str(TOOLS.parent/'packaged70/browser.cjs')],env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
  records[label]=read(proof/'browser-result.json')
 state=query(url,'/api/state');assert state['ready']
 baseline=hashes(case);(OUT/'request-restart').touch();wait(lambda:(OUT/'guide-restarted.json').exists(),'guide replay',100)
 assert hashes(case)==baseline
 for label,intent in [('ha','sh2-129_ha'),('oiii','ou4_oiii')]:
  proof=case/('ui-reopen-'+label);proof.mkdir();env.update(CASE_PROOF=str(proof),UI_INTENT=intent,BROWSER_MODE='reopen',MISSION_ID=records[label]['accepted']['body']['mission_id'],EXECUTION_ID=records[label]['session']['execution']['execution_id'])
  with (proof/'driver.log').open('w',encoding='utf-8') as f:subprocess.run(['node',str(TOOLS.parent/'packaged70/browser.cjs')],env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
 assert hashes(case)==baseline
 (OUT/'request-export').touch();state=wait(lambda:read(OUT/'guide-finished.json') if (OUT/'guide-finished.json').exists() else None,'guide export',90)
 archive=Path(state['exported'])
 with zipfile.ZipFile(archive) as z:
  result=json.loads(z.read('qualification.json'));assert result['verdict']=='PASS_LAB';assert len(result['replays'])==6
  permissions=json.loads(z.read('browser-permissions.json'))
  assert permissions['status']==('configured' if os.name=='nt' else 'not_required')
  if os.name=='nt':
   assert permissions['exit_code']==78 and permissions['sandbox_disabled'] is False
   assert 'Sandbox cannot access executable' not in z.read('browser.log').decode(errors='replace')
   assert 'Network service crashed or was terminated' not in z.read('browser.log').decode(errors='replace')
  assert not any(n.endswith('.key') or 'user_profile' in n or 'browser-profile' in n for n in z.namelist())
 assert hashes(case)==baseline
 (OUT/'request-close').touch();guide.wait(timeout=30);assert guide.returncode==0;child.wait(timeout=30);assert child.returncode==0;log.close();glog.close()
 # Resume the same completed copy, with no configuration or session regeneration.
 child,again,location,log=start(True);assert again==case;url=location['url'];token=location['token'];assert query(url,'/api/state')['ready'] and hashes(case)==baseline
 query(url,'/api/restart',{'confirmed':True},token);assert hashes(case)==baseline
 resumed=query(url,'/api/export',{'confirmed':True},token)
 with zipfile.ZipFile(resumed['exported']) as z:assert json.loads(z.read('qualification.json'))['verdict']=='PASS_LAB'
 assert hashes(case)==baseline
 query(url,'/api/close',{},token);child.wait(timeout=30);assert child.returncode==0;log.close()
 assert (forbidden/'user_profile.json').read_bytes()==before and not (forbidden/'attestation.json').exists()
 with socket.socket() as s:assert s.connect_ex(('127.0.0.1',8000))!=0,'Listener remains'
 # Export only public logs/results, not profiles, certificates, nonce or browser caches.
 for p in (KIT/'RESULTATS').glob('*.zip'): (OUT/p.name).write_bytes(p.read_bytes())
 for label in ('ha','oiii'):
  for mode in ('accept','reopen'):
   src=case/('ui-'+mode+'-'+label);dest=OUT/src.name;dest.mkdir()
   for name in ('browser-result.json','ui.png','ui.txt','paint-state.json','driver.log'):
    if (src/name).exists():(dest/name).write_bytes((src/name).read_bytes())
 write(OUT/'result.json',{'result':'PASS_LAB','source_sha':read(KIT/'kit.json')['source_sha'],'real_frozen_controller':True,'real_guide_dom':True,'real_candidate_dom':True,'restarts':2,'credit_replays':12,'resume_same_copy':True,'canonical_bytes_unchanged':True,'external_sentinel_unchanged':True,'physical_user_test_pending':True})
finally:
 if case and case.exists():
  for src in case.glob('ui-*'):
   dest=OUT/('debug-'+src.name);dest.mkdir(exist_ok=True)
   for name in ('driver.log','browser.log','browser-result.json','failure-state.json','failure.png','paint-state.json','ui.png','ui.txt','navigation.json'):
    p=src/name
    if p.is_file():(dest/name).write_bytes(p.read_bytes())
  for name in ('controller.log','browser.log','application-stdout.log','application-stderr.log'):
   p=case/name
   if p.is_file():(OUT/('runtime-'+name)).write_bytes(p.read_bytes())
 if guide and guide.poll() is None:guide.terminate();guide.wait(timeout=20)
 if child and child.poll() is None:
  try:query(location['url'],'/api/close',{},location['token']);child.wait(timeout=30)
  except Exception:child.terminate();child.wait(timeout=20)
