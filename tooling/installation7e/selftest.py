from pathlib import Path
import os,sys,subprocess,json,time,zipfile,hashlib,urllib.request,socket
KIT=Path(os.environ['INSTALL_KIT']);OUT=Path(os.environ['INSTALL_PROOF']);OUT.mkdir();TOOLS=Path(__file__).parent
EXE=KIT/'TestController'/('TestController.exe' if os.name=='nt' else 'TestController')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def wait(fn,seconds=400):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  v=fn()
  if v:return v
  time.sleep(.3)
 raise RuntimeError('Timeout installation qualification')
def hashes(case):return {p.relative_to(case/'data').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (case/'data').rglob('*.json') if p.relative_to(case/'data').parts[0]!='Logs'}
forbidden=OUT/'forbidden';forbidden.mkdir();sentinel=forbidden/'profile.json';sentinel.write_text('PUBLIC EXTERNAL SENTINEL');original=sentinel.read_bytes()
env=os.environ.copy();env['ASTROPILOT_DATA_DIR']=str(forbidden);env['NIGHTMERIT_FOREIGN']='DO_NOT_USE'
log=(OUT/'controller.log').open('wb');child=None;guide=None
try:
 child=subprocess.Popen([str(EXE),'--laboratory'],cwd=KIT,env=env,stdout=log,stderr=log)
 case=Path(wait(lambda:read(KIT/'derniere-copie.json')['path'] if (KIT/'derniere-copie.json').exists() else None));location=wait(lambda:read(case/'guide-location.json') if (case/'guide-location.json').exists() else None)
 env.update(CASE_ROOT=str(case),CASE_PROOF=str(OUT),PRODUCT_SOURCE=os.environ['PRODUCT_SOURCE'],NIGHT_CHAIN_URL=location['url'],CHROME_BINARY=str(KIT/read(KIT/'kit.json')['browser']))
 glog=(OUT/'guide-driver.log').open('wb');guide=subprocess.Popen(['node',str(TOOLS/'guide_test.cjs')],env=env,stdout=glog,stderr=glog)
 state=wait(lambda:read(OUT/'guide-ready.json') if (OUT/'guide-ready.json').exists() else None)
 assert state['automatic_installation_pass'];baseline=hashes(case);sessions=urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/v1/execution-sessions');sessions=json.load(sessions)
 assert len(sessions)==2
 fixture={'zone':'Europe/Zurich','night_date':state['night_date'],'availability':state['availability']};(case/'fixture.json').write_text(json.dumps(fixture))
 for label,intent in [('ha','sh2-129_ha'),('oiii','ou4_oiii')]:
  row=next(s for s in sessions if s['acquisition_intent_id']==intent);proof=OUT/('ui-reopen-'+label);proof.mkdir()
  env.update(CASE_PROOF=str(proof),NIGHT_CHAIN_URL='http://127.0.0.1:8000',UI_INTENT=intent,BROWSER_MODE='reopen',MISSION_ID=row['mission_id'],EXECUTION_ID=row['execution']['execution_id'])
  with (proof/'driver.log').open('wb') as f:subprocess.run(['node',str(TOOLS.parent/'packaged70/browser.cjs')],env=env,stdout=f,stderr=f,check=True,timeout=180)
 assert hashes(case)==baseline
 (OUT/'request-export').touch();state=wait(lambda:read(OUT/'guide-finished.json') if (OUT/'guide-finished.json').exists() else None)
 archive=Path(state['exported'])
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None;q=json.loads(z.read('qualification.json'));assert q['verdict']=='PASS_LAB' and q['automatic_installation_pass'] and q['canonical_bytes_unchanged'] and not q['real_profile_accessed']
  assert len(q['automatic_checks']['upgrade_replays'])==6 and len(q['automatic_checks']['reinstall_replays'])==6
  assert all(r['status']=='already_applied' for group in q['automatic_checks'].values() for r in group)
  assert q['runtime_identity']['build']=='7e98e45';assert len(q['sessions'])==2
 assert hashes(case)==baseline and sentinel.read_bytes()==original
 (OUT/archive.name).write_bytes(archive.read_bytes());(OUT/'request-close').touch();guide.wait(timeout=30);assert guide.returncode==0;child.wait(timeout=30);assert child.returncode==0
 with socket.socket() as s:assert s.connect_ex(('127.0.0.1',8000))!=0
 (OUT/'result.json').write_text(json.dumps({'result':'PASS_LAB','source_sha':q['source_sha'],'baseline_source_sha':q['baseline_source_sha'],'operations':q['operations'],'credits_seconds':{s['acquisition_intent_id']:s['current_acquired_seconds'] for s in q['sessions']},'credit_replays':12,'canonical_bytes_unchanged':True,'external_sentinel_unchanged':True,'real_guide_dom':True,'real_candidate_dom':True,'windows_sandbox_physical_pending':os.name=='nt','physical_user_test_pending':True},indent=2))
finally:
 for p in case.glob('*.log') if 'case' in locals() else []:
  if p.is_file():(OUT/('runtime-'+p.name)).write_bytes(p.read_bytes())
 if guide and guide.poll() is None:guide.terminate();guide.wait(timeout=20)
 if child and child.poll() is None:child.terminate();child.wait(timeout=20)
 log.close()
