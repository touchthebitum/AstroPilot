"""Own-process Mac beta launcher. Real weather, empty dedicated profile, no NAS integration."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse, fcntl, hashlib, json, os, secrets, signal, socket, subprocess, sys, threading, time, urllib.request
SHA='__SOURCE_SHA__'
ROOT=Path(sys.executable).resolve().parents[1] if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def write(path,value):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');temp.chmod(0o600);os.replace(temp,path)
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def owners(port):
 r=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{port}','-sTCP:LISTEN','-t'],capture_output=True,text=True,timeout=10)
 return {int(p) for p in r.stdout.split() if p.isdigit()}
def verify(root):
 meta=json.loads((root/'manifest.json').read_text());assert meta['source_sha']==SHA
 for rel,record in meta['files'].items():
  p=root/rel
  if not p.resolve().is_relative_to(root.resolve()):raise RuntimeError('Chemin hors de la copie refusé.')
  if 'link' in record:
   if not p.is_symlink() or os.readlink(p)!=record['link']:raise RuntimeError('Lien modifié : '+rel)
  elif not p.is_file() or digest(p)!=record['sha256']:raise RuntimeError('Fichier modifié : '+rel)
 return meta

def environment(case,launcher):
 env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_')) and k.upper() not in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','SSL_CERT_FILE','SSL_CERT_DIR')}
 for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','MPLCONFIGDIR'):
  p=case/'environment'/key;p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
 env['ASTROPILOT_DATA_DIR']=str(case/'profil');env['BROWSER']=f'"{launcher}" --ignore-browser %s'
 return env

def browser_arguments(chrome,case):
 # This dedicated local browser has no account/password use. Chromium's test
 # keychain avoids any access to the user's macOS keychain (as in Playwright).
 return [str(chrome),'--no-first-run','--no-default-browser-check',
         '--disable-background-networking','--use-mock-keychain',
         '--user-data-dir='+str(case/'navigateur')]

def terminate_owned(child):
 if child and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=20)
  except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)

def stop(root):
 p=root/'DONNEES-BETA/controle.json'
 if not p.is_file():print('La copie bêta est déjà arrêtée.');return
 control=json.loads(p.read_text())
 if owners(control['port'])!={control['pid']}:raise RuntimeError('Le lanceur indiqué ne répond plus ; aucun autre processus ne sera contacté.')
 req=urllib.request.Request(f"http://127.0.0.1:{control['port']}/stop",data=b'{}',headers={'X-Beta-Token':control['token']},method='POST')
 with OPENER.open(req,timeout=5) as response:assert response.status==200
 print('Arrêt demandé uniquement à la copie bêta privée.')

def start(root,selftest=False,data_transfer=False):
 if selftest and data_transfer:raise RuntimeError('Modes de vérification et de reprise incompatibles.')
 verify(root)
 case=root/('VERIFICATIONS/'+secrets.token_hex(6) if selftest else 'DONNEES-BETA');case.mkdir(parents=True,exist_ok=True)
 lock=(case/'lanceur.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise RuntimeError('Cette copie bêta est déjà lancée.')
 exe=root/'candidate/AstroPilot.app/Contents/MacOS/AstroPilot'
 chrome=root/'browser/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
 env=environment(case,Path(sys.executable));app=browser=None;logs=[];server=None;thread=None;done=threading.Event();control_file=case/'controle.json';token=secrets.token_urlsafe(32)
 for name in ('SIGINT','SIGTERM','SIGHUP'):signal.signal(getattr(signal,name),lambda *_:done.set())
 try:
  if owners(8000):raise RuntimeError('Une application occupe le port 8000. Fermez-la normalement puis relancez cette copie. Aucun processus existant n’a été arrêté.')
  with socket.socket() as s:
   if s.connect_ex(('127.0.0.1',8000))==0:raise RuntimeError('Le port 8000 est occupé.')
  for name in ('application-stdout.log','application-stderr.log'):logs.append((case/name).open('ab'))
  app=subprocess.Popen([str(exe)]+(['--data-transfer'] if data_transfer else []),cwd=case,env=env,stdout=logs[0],stderr=logs[1],start_new_session=True)
  identity=None
  for _ in range(240):
   if app.poll() is not None:raise RuntimeError('La copie NightMerit s’est arrêtée au lancement.')
   try:
    with OPENER.open('http://127.0.0.1:8000/v1/runtime-identity',timeout=1) as r:identity=json.load(r)
   except OSError:time.sleep(.25);continue
   if identity!={'application':'astropilot','architecture':'arm64','build':SHA[:7],'version':'1.0.0b8'} or owners(8000)!={app.pid}:raise RuntimeError('Identité ou propriétaire du serveur incorrect.')
   break
  else:raise RuntimeError('Délai de lancement dépassé.')
  browser_case=case
  if data_transfer:
   browser_case=case/'assistant-donnees'
   preferences=browser_case/'navigateur/Default/Preferences'
   preferences.parent.mkdir(parents=True,exist_ok=True)
   downloads=case/'SAUVEGARDES';downloads.mkdir(mode=0o700,exist_ok=True);downloads.chmod(0o700)
   # Dedicated browser profile only; no personal browser preferences are touched.
   preferences.write_text(json.dumps({'download':{'default_directory':str(downloads),'prompt_for_download':False}}))
  base=browser_arguments(chrome,browser_case)
  if selftest:
   with OPENER.open('http://127.0.0.1:8000/v1/configuration',timeout=10) as r:config=json.load(r)
   assert not config['configured'],'Le contrôle initial doit rester sans configuration métier.'
   result=subprocess.run(base+['--headless=new','--disable-gpu','--dump-dom','--timeout=20000','http://127.0.0.1:8000/'],cwd=case,env=env,capture_output=True,timeout=40)
   (case/'browser-stderr.log').write_bytes(result.stderr)
   (case/'browser-dom.html').write_bytes(result.stdout)
   assert result.returncode==0 and b'NightMerit' in result.stdout,'Le navigateur isolé ne montre pas NightMerit.'
   write(case/'result.json',{'result':'PASS','source_sha':SHA,'identity':identity,'profile_initially_unconfigured':True,'no_prefilled_equipment_site_or_availability':True,'weather_mode':'real_unmodified_product_no_proxy_or_fixture','forecast_request_exercised':False,'own_server_pid_verified':True,'browser_sandbox_disabled':False,'real_profile_or_nas_used':False})
   print('Vérification réussie : application et navigateur isolés, configuration initiale vide.',flush=True)
   return
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*_):pass
   def do_POST(self):
    if self.path!='/stop' or not secrets.compare_digest(self.headers.get('X-Beta-Token',''),token):self.send_error(403);return
    self.send_response(200);self.end_headers();self.wfile.write(b'OK');done.set()
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  write(control_file,{'pid':os.getpid(),'port':server.server_address[1],'token':token})
  browser_log=(case/'browser.log').open('ab');logs.append(browser_log)
  browser=subprocess.Popen(base+['http://127.0.0.1:8000/'],cwd=case,env=env,stdout=browser_log,stderr=browser_log,start_new_session=True)
  print('NightMerit bêta privée — profil dédié — météo réelle\nGardez cette fenêtre ouverte. Pour arrêter : ARRETER-BETA.command.\nVos saisies seront conservées uniquement dans DONNEES-BETA.',flush=True)
  while not done.wait(.5):
   if app.poll() is not None:
    if data_transfer and app.returncode==0:break
    raise RuntimeError('NightMerit s’est arrêté ; les journaux de cette copie sont conservés.')
   if browser.poll() is not None:break
 finally:
  if server:server.shutdown();server.server_close()
  if thread:thread.join(timeout=5)
  terminate_owned(browser);terminate_owned(app)
  for log in logs:log.close()
  if control_file.is_file():
   try:
    if json.loads(control_file.read_text()).get('token')==token:control_file.unlink()
   except (OSError,ValueError):pass
  if app:
   for _ in range(100):
    if not owners(8000):break
    time.sleep(.1)
   else:raise RuntimeError('Le port ne s’est pas libéré après arrêt de notre copie.')
  fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

if __name__=='__main__':
 if '--ignore-browser' in sys.argv:sys.exit(0)
 parser=argparse.ArgumentParser();parser.add_argument('--data-transfer',action='store_true');parser.add_argument('--stop',action='store_true');parser.add_argument('--verify-only',action='store_true');parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
 try:
  if args.stop:stop(ROOT)
  elif args.verify_only:verify(ROOT);print('Copie et empreintes vérifiées.')
  else:start(ROOT,args.self_test,args.data_transfer)
 except Exception as error:print('Arrêt : '+str(error),file=sys.stderr,flush=True);sys.exit(1)
