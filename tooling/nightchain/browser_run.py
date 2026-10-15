from common import *
import urllib.request,subprocess,time,socket
seed();before=profile_hash()
with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',8000))!=0,'Existing server on qualification port'
log=(CASE/'server.log').open('wb')
child=subprocess.Popen([sys.executable,'-B','-m','uvicorn','server:application','--app-dir',str(Path(__file__).parent),'--host','127.0.0.1','--port','8000'],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=log)
try:
 for _ in range(300):
  assert child.poll() is None,'Server exited'
  try:
   with urllib.request.urlopen('http://127.0.0.1:8000/v1/configuration',timeout=1) as response:assert response.status==200
   break
  except OSError:time.sleep(.2)
 else:raise AssertionError('Server startup timeout')
 r=subprocess.run([os.environ.get('NODE_BINARY','node'),str(Path(__file__).with_name('browser.cjs'))],env=os.environ.copy(),timeout=180);assert r.returncode==0,'Browser scenario failed'
finally:
 child.terminate();child.wait(timeout=30);log.close()
 pidfile=CASE/'browser-pid.json'
 if pidfile.exists():
  pid=json.loads(pidfile.read_text())['pid']
  if os.name=='nt':subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True)
  else:
   import signal
   try:os.kill(pid,signal.SIGTERM)
   except ProcessLookupError:pass
if os.environ['UI_INTENT']!='site_changed':assert profile_hash()==before
with TestClient(app()) as c:
 result=json.loads((CASE/'browser-result.json').read_text());current=c.get('/v1/accepted-mission/current');assert current.status_code==200,current.json()
 if os.environ['UI_INTENT']=='site_changed':assert current.json() is None
 else:assert current.json()['mission_id']==result['accepted']['body']['mission_id'],current.json()
 sessions=c.get('/v1/execution-sessions').json();assert sessions==[],sessions
 result.update(restart_mission_preserved=True,profile_unchanged=os.environ['UI_INTENT']!='site_changed',no_execution_or_credit=True)
 (CASE/'browser-result.json').write_text(json.dumps(result,indent=2)+'\n')
print('Browser',os.environ['UI_INTENT'],'PASS')
