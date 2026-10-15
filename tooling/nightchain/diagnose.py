from pathlib import Path
import http.server,threading,json,os,subprocess,sys
assert os.environ.get('GITHUB_ACTIONS')=='true','Disposable runner only'
root=Path(os.environ['RUNNER_TEMP'])/'mac-browser-diagnosis';root.mkdir()
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  with (root/'requests.jsonl').open('a') as f:f.write(json.dumps({'path':self.path})+'\n')
  body=b'<html><body><h1 id="proof">LOCAL STATIC OK</h1></body></html>'
  self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8000),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 for mode in ('isolated','short_tmp','native_home','native_tmp','no_proxy'):
  case=root/mode;case.mkdir();env=os.environ.copy();env.update(CASE_ROOT=str(case),DIAGNOSTIC_MODE=mode)
  for key in ('HOME','TMP','TEMP','TMPDIR'):
   p=case/key;p.mkdir();env[key]=str(p)
  if mode=='short_tmp':
   import tempfile
   short=Path(tempfile.mkdtemp(prefix='nm-',dir='/tmp'));env.update(TMPDIR=str(short),TMP=str(short),TEMP=str(short))
  if mode=='native_home':env['HOME']=os.environ['NATIVE_TEST_HOME']
  if mode=='native_tmp':env['TMPDIR']=os.environ['NATIVE_TEST_TMPDIR']
  with (case/'driver.log').open('wb') as f:
   p=subprocess.run([os.environ.get('NODE_BINARY','node'),str(Path(__file__).with_name('diagnose.cjs'))],env=env,stdout=f,stderr=f,timeout=100)
  print(mode,p.returncode,(case/'diagnosis.json').read_text() if (case/'diagnosis.json').exists() else 'no diagnosis',flush=True)
finally:server.shutdown();server.server_close()
