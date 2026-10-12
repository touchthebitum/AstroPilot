"""Read-only weather comparisons; all application state is synthetic runner temp."""
import concurrent.futures,datetime,hashlib,json,os,pathlib,shutil,socket,ssl,subprocess,sys,time,urllib.request,urllib.error,urllib.parse,zipfile
source=pathlib.Path.cwd();temp=pathlib.Path(os.environ['RUNNER_TEMP']);root=temp/'weather-f70-diagnostic';root.mkdir();out=root/'results';out.mkdir();sha='f70f2e4476b4ae7b58d1275615b9d4cd6d725ce2'
artifact=next((temp/'weather-download').rglob('AstroPilot-1.0.0b8-windows-x86_64-portable.zip'))
assert hashlib.sha256(artifact.read_bytes()).hexdigest()=='8e32e960c41475db242d6b6fd2fc2a07fa515e993148aaf14ebb3a8c4fbda777'
with zipfile.ZipFile(artifact) as z:assert z.testzip() is None;z.extractall(root/'extracted')
exe=root/'extracted/AstroPilot/AstroPilot.exe'
for key in ['HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME']:
 d=root/key;d.mkdir();os.environ[key]=str(d)
noop=root/'noop.py';noop.write_text('pass\n');os.environ['BROWSER']=f'"{sys.executable}" "{noop}" %s'
sys.path.insert(0,str(source))
import requests,certifi,astro_score
from types import SimpleNamespace
base='https://api.open-meteo.com/v1/forecast'
params={'latitude':40.4,'longitude':-3.7,'timezone':'Europe/Madrid','forecast_days':7,'temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm','timeformat':'unixtime','hourly':','.join(['cloud_cover','cloud_cover_low','cloud_cover_mid','cloud_cover_high','precipitation','relative_humidity_2m','visibility','wind_speed_10m','temperature_2m'])}
url=base+'?'+urllib.parse.urlencode(params)
current=base+'?'+urllib.parse.urlencode({'latitude':40.4,'longitude':-3.7,'current':'rain,showers,wind_speed_10m,wind_gusts_10m,relative_humidity_2m,temperature_2m,dew_point_2m','timezone':'UTC','timeformat':'unixtime','temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm','forecast_days':1})
curl=shutil.which('curl.exe');assert curl
report={'product_sha':sha,'artifact_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'forecast_url':url,'current_url':current,'tls_verified':True,'source_ssl':ssl.OPENSSL_VERSION,'requests_version':requests.__version__,'ca_sha256':hashlib.sha256(pathlib.Path(certifi.where()).read_bytes()).hexdigest(),'curl_version':subprocess.check_output([curl,'--version'],text=True),'proxy_env_present':{k:bool(os.environ.get(k)) for k in ['HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE']},'rounds':[]}
real_get=requests.get
source_errors=[]
def traced_get(*args,**kw):
 try:return real_get(*args,**kw)
 except Exception as e:source_errors.append({'type':type(e).__name__,'repr':repr(e)});raise
astro_score.requests=SimpleNamespace(get=traced_get,exceptions=requests.exceptions)
def raw(u):
 t=time.monotonic()
 try:
  r=real_get(u,timeout=15,verify=certifi.where());r.raise_for_status();payload=r.json();return {'http':r.status_code,'seconds':time.monotonic()-t,'bytes':len(r.content),'json_keys':list(payload)}
 except Exception as e:return {'seconds':time.monotonic()-t,'error_type':type(e).__name__,'error':repr(e)}
def curl_request(u,label):
 t=time.monotonic();body=out/(label+'.body');r=subprocess.run([curl,'--silent','--show-error','--connect-timeout','15','--max-time','30','--output',str(body),'--write-out','%{json}',u],capture_output=True,text=True,timeout=40)
 try:metrics=json.loads(r.stdout)
 except ValueError:metrics={'output':r.stdout[:500]}
 keep=['http_code','remote_ip','time_namelookup','time_connect','time_appconnect','time_starttransfer','time_total','ssl_verify_result','errormsg']
 return {'exit':r.returncode,'seconds':time.monotonic()-t,'stderr':r.stderr[:2000],'metrics':{k:metrics.get(k) for k in keep},'bytes':body.stat().st_size if body.exists() else 0}
def source_fetch():
 t=time.monotonic();source_errors.clear()
 try:w=astro_score.fetch_weather(40.4,-3.7);return {'seconds':time.monotonic()-t,'valid_snapshot':w is not None,'errors':list(source_errors)}
 except Exception as e:return {'seconds':time.monotonic()-t,'error_type':type(e).__name__,'error':repr(e),'errors':list(source_errors)}
local=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def binary_tonight():
 t=time.monotonic();req=urllib.request.Request('http://127.0.0.1:8000/v1/tonight',data=json.dumps({'availability':{'mode':'all_night'}}).encode(),headers={'Content-Type':'application/json'})
 try:
  with local.open(req,timeout=180) as r:status,payload=r.status,json.load(r)
 except urllib.error.HTTPError as e:status,payload=e.code,json.loads(e.read())
 return {'seconds':time.monotonic()-t,'http':status,'status':payload.get('status'),'detail':payload.get('detail'),'creation_refusal':payload.get('creation_refusal')}
def worker(label):
 t=time.monotonic();f=out/(label+'-worker.json');r=subprocess.run([str(exe),'--guardian-http-worker','40.4','-3.7','15',str(f)],capture_output=True,text=True,timeout=45)
 return {'seconds':time.monotonic()-t,'exit':r.returncode,'stderr':r.stderr[:1000],'has_weather':f.exists()}
children=[]
try:
 for mode,count in [('clean',3),('invalid_ssl_env',1)]:
  for k in ['SSL_CERT_FILE','SSL_CERT_DIR']:os.environ.pop(k,None)
  if mode=='invalid_ssl_env':os.environ['SSL_CERT_FILE']='C:/nonexistent/validation-ca.pem';os.environ['SSL_CERT_DIR']='C:/nonexistent/validation-certs'
  data=pathlib.Path(os.environ['ASTROPILOT_DATA_DIR']);(data/'user_profile.json').write_text(json.dumps({'location':{'name':'Synthetic Madrid diagnostic','latitude':40.4,'longitude':-3.7},'preferences':{'bortle':4},'active_equipment':'samyang_183','available_equipment':['samyang_183'],'projects':{},'sessions':[],'profile_revision':1}),encoding='utf-8')
  with socket.socket() as s:s.bind(('127.0.0.1',8000))
  log=(out/(mode+'-binary.log')).open('w',encoding='utf-8');child=subprocess.Popen([str(exe)],cwd=root,env=os.environ.copy(),stdout=log,stderr=log);children.append(child)
  for _ in range(120):
   try:
    identity=json.load(local.open('http://127.0.0.1:8000/v1/runtime-identity',timeout=2));assert identity['build']=='f70f2e4';report['runtime_identity']=identity;break
   except Exception:
    assert child.poll() is None;time.sleep(.5)
  else:raise RuntimeError('binary_not_ready')
  for n in range(count):
   label=f'{mode}-{n+1}';began=datetime.datetime.now(datetime.timezone.utc).isoformat()
   tasks={'binary_tonight':binary_tonight,'source_fetch':source_fetch,'requests_forecast':lambda:raw(url),'curl_forecast':lambda:curl_request(url,label+'-forecast'),'requests_current':lambda:raw(current),'curl_current':lambda:curl_request(current,label+'-current'),'binary_current_worker':lambda:worker(label)}
   with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
    futures={k:pool.submit(v) for k,v in tasks.items()};results={k:f.result() for k,f in futures.items()}
   report['rounds'].append({'mode':mode,'round':n+1,'started_utc':began,'results':results});(out/'comparison.json').write_text(json.dumps(report,indent=2));print(label,json.dumps(results),flush=True)
   time.sleep(3)
  child.terminate();child.wait(timeout=20);log.close()
except Exception as e:report['error']=repr(e);raise
finally:
 for child in children:
  if child.poll() is None:child.terminate();child.wait(timeout=20)
 report['children_reaped']=all(c.poll() is not None for c in children);(out/'comparison.json').write_text(json.dumps(report,indent=2))
