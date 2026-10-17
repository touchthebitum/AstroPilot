"""Physical-machine test kit. No imports from NightMerit or access to real profiles."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo,reset_tzpath
import argparse,hashlib,json,os,secrets,shutil,socket,subprocess,sys,threading,time,traceback,urllib.request,urllib.error,zipfile
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from forecast import Forecast
from browser_permissions import configure_browser, browser_environment
import tzdata
reset_tzpath(())
SHA='7e98e45b2f46f57dcf959f3bf8d2b1373375cf48'
AUTH='c5bc501f192e0894008277cc4b76957a10d37cac092de4f318a7eed0a2c382d5'
URL='http://127.0.0.1:8000';OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))
SITES={'zurich':{'name':'TEST ISOLE Zurich','latitude':46.888,'longitude':6.55,'bortle':4,'timezone':'Europe/Zurich'},'winnipeg':{'name':'TEST ISOLE Winnipeg','latitude':49.895,'longitude':-97.138,'bortle':4,'timezone':'America/Winnipeg'}}

def write(path,value):
 temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');os.replace(temp,path)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def authority(path):return {p.relative_to(path).as_posix():digest(p) for p in sorted(path.rglob('*.json')) if p.relative_to(path).parts[0]!='Logs'}
def request(method,path,body=None):
 req=urllib.request.Request(URL+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
 try:
  with OPENER.open(req,timeout=20) as r:return json.load(r)
 except urllib.error.HTTPError as e:raise RuntimeError('Réponse '+str(e.code)+' : '+e.read().decode('utf-8',errors='replace')) from e

def verify(root):
 manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
 if manifest['source_sha']!=SHA:raise RuntimeError('Le kit ne correspond pas à main 7e98e45.')
 for rel,record in manifest['files'].items():
  path=root/rel
  if not path.resolve().is_relative_to(root.resolve()):raise RuntimeError('Chemin hors du kit refusé.')
  if 'link' in record:
   if not path.is_symlink() or os.readlink(path)!=record['link']:raise RuntimeError('Lien du kit modifié : '+rel)
  elif not path.is_file() or digest(path)!=record['sha256']:raise RuntimeError('Fichier du kit manquant ou modifié : '+rel)
 return manifest

@contextmanager
def external_dll_search():
 # Frozen Windows programs must not give their DLL search path to Chrome,
 # its directory-only setup helper, or another independent bundle.
 if os.name=='nt' and getattr(sys,'frozen',False):
  import ctypes
  kernel=ctypes.windll.kernel32;buffer=ctypes.create_unicode_buffer(32768)
  kernel.GetDllDirectoryW(len(buffer),buffer);previous=buffer.value
  kernel.SetDllDirectoryW(None)
  try:yield
  finally:kernel.SetDllDirectoryW(previous or None)
 else:yield

def spawn(args,**kwargs):
 with external_dll_search():return subprocess.Popen(args,**kwargs)

def run_external(args,**kwargs):
 with external_dll_search():return subprocess.run(args,**kwargs)

class App:
 def __init__(self,kit,case,forecast):self.kit=kit;self.case=case;self.forecast=forecast;self.child=None;self.logs=[]
 def env(self):
  env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_')) and k.upper() not in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY','REQUESTS_CA_BUNDLE')}
  for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','MPLCONFIGDIR'):
   p=self.case/'environment'/key;p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
  env['ASTROPILOT_DATA_DIR']=str(self.case/'data');env['BROWSER']='"'+str(self.kit/'TestController'/('TestController.exe' if os.name=='nt' else 'TestController'))+'" --ignore-browser %s'
  env.update(self.forecast.env);return env
 def owners(self):
  args=['powershell','-NoProfile','-Command',"Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"] if os.name=='nt' else ['/usr/sbin/lsof','-nP','-iTCP:8000','-sTCP:LISTEN','-t']
  r=subprocess.run(args,capture_output=True,text=True,timeout=20)
  return {int(x) for x in r.stdout.split() if x.isdigit()}
 def owned(self):
  if not self.child or self.child.poll() is not None:raise RuntimeError('La copie de test est arrêtée. Aucune autre instance ne sera utilisée.')
 def start(self):
  if self.owners():raise RuntimeError('Le port 8000 est occupé. Fermez normalement une autre instance NightMerit puis relancez ce kit. Aucun processus existant n’a été arrêté.')
  with socket.socket() as s:
   if s.connect_ex(('127.0.0.1',8000))==0:raise RuntimeError('Le port de test est déjà utilisé.')
  exe=getattr(self,'executable',self.kit/'candidate'/('AstroPilot.exe' if os.name=='nt' else 'AstroPilot.app/Contents/MacOS/AstroPilot'))
  logs=[(self.case/'application-stdout.log').open('ab'),(self.case/'application-stderr.log').open('ab')];self.logs=logs
  self.child=spawn([str(exe)],cwd=self.case,env=self.env(),stdout=logs[0],stderr=logs[1])
  try:
   for _ in range(240):
    self.owned()
    try:identity=request('GET','/v1/runtime-identity')
    except (OSError,urllib.error.URLError):time.sleep(.25);continue
    if identity.get('build')!=getattr(self,'expected_sha',SHA)[:7] or identity.get('application')!='astropilot' or self.owners()!={self.child.pid}:raise RuntimeError('Identité de la copie ou propriétaire du serveur incorrect.')
    with OPENER.open(URL+'/v1/configuration',timeout=20) as r:
     if r.headers.get('X-NightMerit-Time-Authority')!=AUTH:raise RuntimeError('Les règles d’heure du candidat ne correspondent pas.')
    self.identity=identity;return
   raise RuntimeError('La copie de test ne répond pas au lancement.')
  except BaseException:self.stop();raise
 def stop(self):
  if not self.child:return
  if self.child.poll() is None:
   self.child.terminate()
   try:self.child.wait(timeout=20)
   except subprocess.TimeoutExpired:self.child.kill();self.child.wait(timeout=10)
  for f in self.logs:f.close()
  self.logs=[]
  for _ in range(100):
   with socket.socket() as s:busy=s.connect_ex(('127.0.0.1',8000))==0
   if not busy:return
   time.sleep(.1)
  raise RuntimeError('Le port de la copie ne s’est pas libéré.')

class Controller:
 def __init__(self,kit,case,lab=False):
  self.kit=kit;self.case=case;self.lab=lab;self.lock=threading.Lock();self.error=None;self.closed=threading.Event();self.closing=False;self.browser=None;self.exported=None
  self.state=json.loads((case/'run.json').read_text(encoding='utf-8')) if (case/'run.json').exists() else {'phase':'new','source_sha':SHA,'user_confirmations':{},'public_test_only':True,'laboratory':lab}
  if self.state['source_sha']!=SHA or not self.state['public_test_only']:raise RuntimeError('La reprise ne désigne pas une copie de test de ce kit.')
  self.lab=self.state['laboratory'];self.forecast=Forecast(case);self.forecast.__enter__();self.app=App(kit,case,self.forecast)
  if self.state.get('site'):
   self.forecast.site=SITES[self.state['site']];self.app.start()
 def save(self):write(self.case/'run.json',self.state)
 def start(self,site):
  if self.state['phase']!='new':raise RuntimeError('Cette copie existe déjà. Utilisez les étapes de reprise sans réinitialiser le profil.')
  if site not in SITES:raise ValueError('Site de test invalide')
  self.forecast.site=SITES[site];self.app.start();s={k:v for k,v in SITES[site].items() if k!='timezone'}
  r=request('PUT','/v1/configuration',{'expected_revision':0,'site':s,'equipment':{'preset_id':'samyang_183'},'projects':{'Sh2-129':{'hours':0,'target_hours':20,'importance':9}}})
  request('PUT','/v1/projects/Sh2-129/progress',{'expected_revision':r['profile_revision'],'imaging_field_id':'sh2-129_ou4','acquisition_intent_progress':[{'acquisition_intent_id':i,'acquired_duration_manual':0} for i in ('sh2-129_ha','ou4_oiii')],'acquisition_intent_targets':[{'acquisition_intent_id':i,'target_hours':6} for i in ('sh2-129_ha','ou4_oiii')]})
  local=datetime.now(timezone.utc).astimezone(ZoneInfo(SITES[site]['timezone']));date=(local.date()+timedelta(days=1)).isoformat()
  self.state.update(site=site,phase='running',availability={'mode':'fixed_window','start_local':date+'T00:30','end_local':date+'T03:30'},night_date=local.date().isoformat());self.save()
 def inspect(self):
  result=dict(self.state);result.update(error=self.error,exported=self.exported,ready=False,app_url=URL+'/?kit='+str(int(time.time())),copy=str(self.case))
  if not self.state.get('site') or self.exported:return result
  self.app.owned();sessions=request('GET','/v1/execution-sessions');progress=request('GET','/v1/projects/Sh2-129/progress')
  totals={r['acquisition_intent_id']:r['effective_total_seconds'] for r in progress['intent_progress_breakdown']}
  expected={'sh2-129_ha':5400,'ou4_oiii':900};checks={}
  for intent,seconds in expected.items():
   rows=[s for s in sessions if s['acquisition_intent_id']==intent]
   checks[intent]={'sessions':len(rows),'total':totals.get(intent),'recorded':len(rows)==1 and rows[0]['execution']['status']=='completed' and rows[0]['credit'] is not None and rows[0]['acquired_after_seconds']==seconds and totals.get(intent)==seconds}
  result.update(checks=checks,ready=len(sessions)==2 and all(c['recorded'] for c in checks.values()))
  self.last_sessions=sessions;self.last_progress=progress
  return result
 def restart(self,confirmed):
  if confirmed is not True:raise ValueError('Cochez la confirmation visuelle des deux crédits.')
  if not self.inspect()['ready']:raise RuntimeError('Les deux crédits attendus ne sont pas encore enregistrés. La copie est conservée pour continuer.')
  self.state['user_confirmations']['before_restart']=True;self.save();before=authority(self.case/'data');write(self.case/'before-restart.json',before)
  sessions=self.last_sessions;self.app.stop();self.app.start();replays=[]
  for s in sessions:
   for _ in range(3):
    self.app.owned()
    if self.app.owners()!={self.app.child.pid}:raise RuntimeError('Le serveur n’appartient plus à cette copie.')
    revision=request('GET','/v1/configuration')['profile_revision'];credit=s['credit']
    r=request('POST','/v1/executions/'+s['execution']['execution_id']+'/intent-progress-credit',{'expected_revision':revision,'evidence_ids':credit['evidence_ids'],'confirm_historical_baseline':False})
    if r['status']!='already_applied':raise RuntimeError('Le rejeu n’a pas conservé le crédit existant.')
    replays.append({'execution_id':s['execution']['execution_id'],'status':r['status']})
  if not self.inspect()['ready'] or authority(self.case/'data')!=before:raise RuntimeError('Le contrôle après reprise n’a pas conservé les données attendues.')
  self.state.update(phase='replayed',replays=replays,canonical_bytes_unchanged=True);self.save()
 def export(self,confirmed=False,incomplete=False):
  if self.exported:return self.exported
  valid=not incomplete and self.state['phase']=='replayed' and confirmed is True and self.inspect()['ready']
  if valid:
   self.state['user_confirmations']['after_restart']=True;self.state['phase']='complete'
  self.save()
  self.app.stop()
  if valid and authority(self.case/'data')!=json.loads((self.case/'before-restart.json').read_text(encoding='utf-8')):raise RuntimeError('Les fichiers canoniques ont changé avant export.')
  verdict='PASS_LAB' if valid and self.lab else 'PASS_PC_DECLARE' if valid else 'NOT_VALIDATED'
  report={**self.state,'verdict':verdict,'physical_ui_confirmation':'declared by operator' if not self.lab else 'laboratory automation, not physical user proof','error':self.error,'runtime_identity':getattr(self.app,'identity',None),'copie_isolee':str(self.case),'kit_source_sha':SHA,'real_profile_accessed':False}
  if hasattr(self,'last_sessions'):report.update(sessions=self.last_sessions,progress=self.last_progress)
  out=self.kit/'RESULTATS';out.mkdir(exist_ok=True);archive=out/('resultats-kit-7e98e45-'+('windows' if os.name=='nt' else 'mac')+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(2)+'.zip')
  with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
   z.writestr('qualification.json',json.dumps(report,indent=2,ensure_ascii=False))
   for rel in ('application-stdout.log','application-stderr.log','weather-log.json','controller.log','browser.log','browser-permissions.json'):
    p=self.case/rel
    if p.is_file():z.write(p,rel)
   for folder in (self.case/'data/Logs',self.case/'environment/HOME/Library/Logs/AstroPilot'):
    for p in folder.glob('*.log'):
     if p.is_file():z.write(p,'application-logs/'+('data-' if folder==self.case/'data/Logs' else 'home-')+p.name)
  self.exported=str(archive);return str(archive)
 def shutdown(self):
  if self.closing:return
  self.closing=True
  try:
   if not self.exported:self.export(incomplete=True)
  finally:
   self.app.stop();self.forecast.__exit__()
   if self.browser and self.browser.poll() is None:
    if os.name=='nt':subprocess.run(['taskkill','/PID',str(self.browser.pid),'/T','/F'],capture_output=True,timeout=15)
    else:self.browser.terminate()
   self.closed.set()

def serve(controller):
 token=secrets.token_urlsafe(24);kit=controller.kit
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def send(self,code,body,kind='application/json; charset=utf-8'):
   data=(json.dumps(body,ensure_ascii=False).encode() if isinstance(body,dict) else body);self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
  def do_GET(self):
   if self.path=='/':
    html=(kit/'Guide.html').read_text(encoding='utf-8').replace('__TOKEN__',token);return self.send(200,html.encode(),'text/html; charset=utf-8')
   if self.path=='/api/state':
    try:
     with controller.lock:r=controller.inspect()
    except Exception as e:r={**controller.state,'error':str(e),'ready':False,'exported':controller.exported,'copy':str(controller.case)}
    return self.send(200,r)
   return self.send(404,{'error':'Introuvable'})
  def do_POST(self):
   if self.headers.get('X-Kit-Token')!=token:return self.send(403,{'error':'Commande du guide refusée.'})
   if self.headers.get('Origin') not in (None,'http://127.0.0.1:'+str(self.server.server_address[1])):return self.send(403,{'error':'Origine refusée.'})
   try:
    body=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),8192)) or b'{}')
    with controller.lock:
     if self.path=='/api/start':controller.start(body.get('site'))
     elif self.path=='/api/restart':controller.restart(body.get('confirmed'))
     elif self.path=='/api/export':controller.export(body.get('confirmed'),body.get('incomplete',False))
     elif self.path=='/api/close':
      self.send(200,{'ok':True});threading.Thread(target=lambda:(time.sleep(.5),controller.shutdown()),daemon=True).start();return
     else:return self.send(404,{'error':'Commande inconnue'})
     self.send(200,controller.inspect())
   except Exception as e:
    controller.error=str(e)
    with (controller.case/'controller.log').open('a',encoding='utf-8') as log:log.write(traceback.format_exc()+'\n')
    self.send(409,{'error':str(e)})
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 write(controller.case/'guide-location.json',{'url':'http://127.0.0.1:'+str(server.server_address[1]),'token':token})
 return server,'http://127.0.0.1:'+str(server.server_address[1])+'/'

def browser(controller,url):
 config=json.loads((controller.kit/'kit.json').read_text(encoding='utf-8'));exe=controller.kit/config['browser']
 env=browser_environment(os.environ)
 try:permissions=configure_browser(controller.kit,run=run_external)
 except Exception as exc:
  controller.error=str(exc)
  write(controller.case/'browser-permissions.json',{'status':'failed','error':str(exc),'sandbox_disabled':False})
  raise
 write(controller.case/'browser-permissions.json',permissions)
 profile=controller.case/'browser-profile';profile.mkdir(exist_ok=True)
 log=(controller.case/'browser.log').open('ab')
 flags=['--headless=new','--disable-gpu','--remote-debugging-port=0'] if controller.lab else []
 controller.browser=spawn([str(exe),'--no-first-run','--no-default-browser-check','--disable-background-networking','--user-data-dir='+str(profile),*flags,url],env=env,stdout=log,stderr=log)

def main():
 if '--ignore-browser' in sys.argv:return
 p=argparse.ArgumentParser();p.add_argument('--resume',action='store_true');p.add_argument('--laboratory',action='store_true');p.add_argument('--no-browser',action='store_true');p.add_argument('--kit-root');p.add_argument('--verify-only',action='store_true');args=p.parse_args()
 kit=Path(args.kit_root).resolve() if args.kit_root else Path(sys.executable).resolve().parent.parent
 print('NightMerit — test isolé de main 7e98e45\nVérification du kit…',flush=True);verify(kit)
 if args.verify_only:
  print('Kit intègre.',flush=True);return
 copies=kit/'COPIES-ISOLEES';copies.mkdir(exist_ok=True)
 if args.resume:
  case=Path(json.loads((kit/'derniere-copie.json').read_text(encoding='utf-8'))['path']).resolve()
  if case.parent!=copies.resolve() or not (case/'TEST-UNIQUEMENT').is_file() or (case/'TEST-UNIQUEMENT').read_text()!=SHA or (case/'data').is_symlink():raise RuntimeError('Copie de reprise absente ou extérieure au kit. Aucun profil ne sera recherché ailleurs.')
 else:
  case=copies/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3));case.mkdir();(case/'TEST-UNIQUEMENT').write_text(SHA);write(kit/'derniere-copie.json',{'path':str(case)})
 controller=Controller(kit,case,args.laboratory);server,url=serve(controller)
 print('Guide du test : '+url+'\nCopie isolée : '+str(case)+'\nGardez cette fenêtre ouverte. Les étapes et l’export se font dans le guide.',flush=True)
 try:
  if not args.no_browser:browser(controller,url)
  while not controller.closed.wait(.25):
   if controller.browser and controller.browser.poll() is not None and not controller.closing:
    controller.error='Le navigateur de test a été fermé ou n’a pas pu démarrer. Un diagnostic incomplet est exporté.';controller.shutdown()
  if controller.exported:print('Résultats : '+controller.exported,flush=True)
 except KeyboardInterrupt:controller.shutdown()
 finally:
  server.shutdown()
  if not controller.closed.is_set():controller.shutdown()
if __name__=='__main__':
 try:main()
 except Exception as exc:
  print('Le test n’est pas validé : '+str(exc),flush=True)
  sys.exit(1)
