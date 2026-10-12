"""Native binary validation only; never install startup jobs or send notifications."""
import argparse,datetime,hashlib,json,os,pathlib,signal,socket,subprocess,sys,time,urllib.request,urllib.error
p=argparse.ArgumentParser();p.add_argument('--binary',required=True);p.add_argument('--work',required=True);p.add_argument('--expected-sha',required=True);p.add_argument('--source',required=True);a=p.parse_args()
root=pathlib.Path(a.work).resolve();root.mkdir(parents=True,exist_ok=False)
exe=pathlib.Path(a.binary).resolve();source=pathlib.Path(a.source).resolve();logs=root/'logs';logs.mkdir()
env=os.environ.copy()
for key,sub in {'HOME':'home','CFFIXED_USER_HOME':'home','USERPROFILE':'home','APPDATA':'appdata','LOCALAPPDATA':'localappdata','ASTROPILOT_DATA_DIR':'data','TMPDIR':'tmp','TMP':'tmp','TEMP':'tmp','XDG_CONFIG_HOME':'config','XDG_CACHE_HOME':'cache','XDG_DATA_HOME':'data','MPLCONFIGDIR':'cache/matplotlib'}.items():
 d=root/sub;d.mkdir(parents=True,exist_ok=True);env[key]=str(d)
for key in ['ASTROPILOT_BUILD_COMMIT','ASTROPILOT_CODESIGN_IDENTITY']:env.pop(key,None)
noop=root/'browser-noop.py';noop.write_text('pass\n');env['BROWSER']=f'"{sys.executable}" "{noop}" %s'
results={'source_sha':a.expected_sha,'binary':str(exe),'checks':{},'isolation':{k:env[k] for k in ['HOME','ASTROPILOT_DATA_DIR','APPDATA','LOCALAPPDATA','TMPDIR']}};processes=[]
def check(k,v):
 results['checks'][k]=bool(v)
 if not v:raise AssertionError(k)
def stamp(seconds=0):return (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=seconds)).isoformat()
def write(path,obj):
 temporary=path.with_suffix('.new');temporary.write_text(json.dumps(obj),encoding='utf-8');temporary.replace(path)
def run(name,args,timeout=60):
 r=subprocess.run([str(exe),*args],env=env,cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
 (logs/(name+'.stdout')).write_text(r.stdout);(logs/(name+'.stderr')).write_text(r.stderr)
 results[name]={'exit':r.returncode};return r
 def_unused=0
def events(name):
 ret=[]
 for line in (logs/(name+'.stdout')).read_text().splitlines():
  try:ret.append(json.loads(line))
  except ValueError:pass
 return ret
def config(provider,timeout=15):
 v={'schema_version':1,'enabled':True,'provider':provider,'interval_seconds':2,'anchor':stamp(1),'notification':{'enabled':False}}
 if provider=='open_meteo_current_v1':v['weather_site']={'latitude':40.4,'longitude':-3.7,'timeout_seconds':timeout}
 return v
def evidence(rain=False):
 values=dict(rain_active=True,rain_eta_minutes=None,wind_kmh=5.0,gust_kmh=8.0,humidity_percent=50.0,dew_spread_c=8.0) if rain else {}
 t=stamp(2)
 return {'observations':{k:{'value':v,'source':'synthetic-isolated-validation','provenance':'OBSERVATION','timestamp':t} for k,v in values.items()},'session_context':{'session_active':True,'observed_at':t}}
def start(name,args):
 stdout=(logs/(name+'.stdout')).open('w');stderr=(logs/(name+'.stderr')).open('w')
 child=subprocess.Popen([str(exe),*args],env=env,cwd=root,stdout=stdout,stderr=stderr);processes.append((child,stdout,stderr));return child
def stop(child):
 if child.poll() is None:
  if sys.platform=='win32':child.terminate()
  else:child.send_signal(signal.SIGTERM)
 try:return child.wait(timeout=20)
 except subprocess.TimeoutExpired:child.kill();child.wait();raise AssertionError('forced kill required')
def cycles(name,count):
 end=time.monotonic()+35
 while time.monotonic()<end:
  c=[x for x in events(name) if x.get('event')=='cycle' and x.get('status')=='COMPLETED']
  if len(c)>=count:return c
  time.sleep(.2)
 raise AssertionError('missing cycles '+name)
try:
 identity=run('identity',['--runtime-identity']);check('identity_exit',identity.returncode==0)
 ident=json.loads(identity.stdout);results['runtime_identity']=ident
 for k,v in {'application':'astropilot','version':'1.0.0b8','build':a.expected_sha[:7],'architecture':'x86_64' if sys.platform=='win32' else 'arm64'}.items():check('identity_'+k,ident.get(k)==v)
 resources=exe.parent/'_internal' if sys.platform=='win32' else exe.parent.parent/'Resources'
 check('certifi_bundled',(resources/'certifi/cacert.pem').is_file())
 for name in ['index.html','app.js','styles.css','help.js','alert-status.js']:
  check('asset_'+name,(resources/'astropilot/web'/name).read_bytes()==(source/'astropilot/web'/name).read_bytes())
 env['SSL_CERT_FILE']='/nonexistent/validation-ca.pem';env['SSL_CERT_DIR']='/nonexistent/validation-certs'
 output=root/'weather.json';results['worker_attempts']=[]
 for attempt in range(1,4):
  began=time.monotonic()
  r=run('worker-'+str(attempt),['--guardian-http-worker','40.4','-3.7','15',str(output)])
  results['worker_attempts'].append({'attempt':attempt,'exit':r.returncode,'elapsed_seconds':round(time.monotonic()-began,3)})
  if r.returncode==0:break
  if attempt<3:time.sleep(10)
 check('worker_exit',r.returncode==0);weather=json.loads(output.read_text());check('worker_weather_fields',isinstance(weather.get('current'),dict) and isinstance(weather.get('current_units'),dict))
 for name,timeout in [('production',15),('timeout',.000001)]:
  cfg=root/(name+'.json');write(cfg,config('open_meteo_current_v1',timeout));r=run(name,['--guardian','--config',str(cfg),'--data-dir',str(root/name),'--once']);ev=events(name);results[name]['events']=ev
  cycle=next(x for x in ev if x.get('event')=='cycle');check(name+'_not_eligible',cycle['decision_eligible'] is False)
  if name=='production':
   results[name]['live_acquisition_succeeded']=r.returncode==0
   check('production_exit_classified',r.returncode in (0,6))
   if r.returncode==6:
    check('production_acquisition_failure_safe',cycle['action']=='EMERGENCY_STOP' and 'evidence_provider_error' in cycle['errors'])
  else:check(name+'_exit',r.returncode==6)
 cfg=root/'injected.json';ep=root/'evidence.json';write(cfg,config('injected_file_v1'));write(ep,evidence())
 args=['--guardian','--config',str(cfg),'--data-dir',str(root/'periodic-state'),'--evidence-file',str(ep)]
 child=start('periodic',args);empty=cycles('periodic',2);check('empty_fail_closed',all(x['risk']=='UNKNOWN' and not x['decision_eligible'] for x in empty));results['empty_cycles']=empty
 concurrent=run('concurrent',args+['--once']);check('host_lock',concurrent.returncode==4)
 write(ep,evidence(True));updated=cycles('periodic',4)[2:];results['rain_cycles']=updated
 check('rain_critical',all(x['risk']=='CRITICAL' and x['action']=='STOP_SESSION' and x['decision_eligible'] for x in updated))
 results['periodic_stop']=stop(child)
 if sys.platform!='win32':check('periodic_clean_sigterm',results['periodic_stop']==0)
 child=start('restart',args);cycles('restart',1);results['restart_stop']=stop(child);results['restart_events']=events('restart')
 old_slots={x['slot'] for x in events('periodic') if x.get('event')=='cycle' and x.get('status')=='COMPLETED'}
 new_slots={x['slot'] for x in events('restart') if x.get('event')=='cycle' and x.get('status')=='COMPLETED'}
 check('no_completed_slot_replay',not old_slots.intersection(new_slots))
 # Isolated web start only after confirming its fixed port is free.
 with socket.socket() as sock:
  sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  sock.bind(('127.0.0.1',8000))
 write(root/'data/user_profile.json',{'location':{'name':'Synthetic validation Madrid','latitude':40.4,'longitude':-3.7},'preferences':{'bortle':4},'active_equipment':'samyang_183','available_equipment':['samyang_183'],'projects':{},'sessions':[],'profile_revision':1})
 child=start('web',[]);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def request(path,body=None):
  req=urllib.request.Request('http://127.0.0.1:8000'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with opener.open(req,timeout=20) as response:return response.status,response.read()
 end=time.monotonic()+60
 while time.monotonic()<end:
  try:status,body=request('/v1/runtime-identity');break
  except Exception:
   if child.poll() is not None:raise AssertionError('web exited')
   time.sleep(.25)
 else:raise AssertionError('web readiness')
 check('web_identity',json.loads(body)==ident);check('web_root',request('/')[0]==200)
 for name,rain in [('api_empty',False),('api_rain',True)]:
  status,body=request('/v1/guardian/evaluate',evidence(rain));results[name]=json.loads(body);check(name+'_http',status==200)
 try:request('/v1/guardian/evaluate',{'observations':{'bad':True}})
 except urllib.error.HTTPError as e:check('invalid_api_422',e.code==422)
 else:raise AssertionError('invalid API accepted')
 for name in ['help.js','alert-status.js']:check('web_serves_'+name,request('/ui/'+name)[1]==(source/'astropilot/web'/name).read_bytes())
 results['web_stop']=stop(child)
except Exception as error:
 results['error']=type(error).__name__+': '+str(error);raise
finally:
 for child,stdout,stderr in processes:
  if child.poll() is None:stop(child)
  stdout.close();stderr.close()
 results['children_reaped']=all(child.poll() is not None for child,_,_ in processes)
 results['status']='passed' if 'error' not in results else 'failed'
 (root/'validation.json').write_text(json.dumps(results,indent=2))
 print(json.dumps({'status':results['status'],'checks':results['checks'],'children_reaped':results['children_reaped']}),flush=True)
