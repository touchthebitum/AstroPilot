"""Correlate fixed-IP, verified-TLS client trials with Windows TCP owner tables."""
import concurrent.futures,ctypes,ctypes.wintypes,datetime,hashlib,json,os,pathlib,shutil,socket,struct,subprocess,sys,threading,time,urllib.request,urllib.error,urllib.parse,zipfile
IP='188.40.99.226';root=pathlib.Path(os.environ['RUNNER_TEMP'])/'weather-fixed-capture';root.mkdir(exist_ok=True);out=root
artifact=next((pathlib.Path(os.environ['RUNNER_TEMP'])/'weather-download').rglob('AstroPilot-1.0.0b8-windows-x86_64-portable.zip'));assert hashlib.sha256(artifact.read_bytes()).hexdigest()=='8e32e960c41475db242d6b6fd2fc2a07fa515e993148aaf14ebb3a8c4fbda777'
with zipfile.ZipFile(artifact) as z:assert z.testzip() is None;z.extractall(root/'extracted')
exe=root/'extracted/AstroPilot/AstroPilot.exe'
for key in ['HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME']:
 d=root/key;d.mkdir();os.environ[key]=str(d)
for key in ['SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE']:os.environ.pop(key,None)
noop=root/'noop.py';noop.write_text('pass\n');os.environ['BROWSER']=f'"{sys.executable}" "{noop}" %s'
import certifi,requests
resolved=sorted({x[4][0] for x in socket.getaddrinfo('api.open-meteo.com',443,type=socket.SOCK_STREAM)});assert resolved==[IP],resolved
params={'latitude':40.4,'longitude':-3.7,'timezone':'Europe/Madrid','forecast_days':7,'temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm','timeformat':'unixtime','hourly':','.join(['cloud_cover','cloud_cover_low','cloud_cover_mid','cloud_cover_high','precipitation','relative_humidity_2m','visibility','wind_speed_10m','temperature_2m'])};url='https://api.open-meteo.com/v1/forecast?'+urllib.parse.urlencode(params)
curl=shutil.which('curl.exe');assert curl
requests_worker=root/'requests_worker.py';requests_worker.write_text('''import requests,certifi,json,sys,time,os
start=time.time()
try:
 r=requests.get(sys.argv[1],timeout=15,verify=certifi.where());r.raise_for_status();body=r.content
 result={'http':r.status_code,'bytes':len(body),'json_valid':isinstance(r.json(),dict)}
except Exception as e:result={'error_type':type(e).__name__,'error':repr(e)}
result.update(pid=os.getpid(),start_epoch=start,end_epoch=time.time());print(json.dumps(result))
''',encoding='utf-8')
gettable=ctypes.WinDLL('iphlpapi').GetExtendedTcpTable;gettable.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.wintypes.ULONG),ctypes.wintypes.BOOL,ctypes.wintypes.ULONG,ctypes.wintypes.ULONG,ctypes.wintypes.ULONG];gettable.restype=ctypes.wintypes.DWORD
samples={};monitor_errors=[];finish=threading.Event()
def monitor():
 while not finish.is_set():
  try:
   size=ctypes.wintypes.ULONG();code=gettable(None,ctypes.byref(size),False,2,5,0);assert code in (0,122),code
   buffer=ctypes.create_string_buffer(size.value);code=gettable(buffer,ctypes.byref(size),False,2,5,0)
   if code==122:continue
   assert code==0,code;data=buffer.raw;count=struct.unpack_from('<I',data)[0];now=time.time()
   for n in range(count):
    state,la,lp,ra,rp,pid=struct.unpack_from('<6I',data,4+n*24);remote=socket.inet_ntoa(struct.pack('<I',ra));port=socket.ntohs(rp&65535)
    if remote==IP and port==443:
     local=socket.inet_ntoa(struct.pack('<I',la));localport=socket.ntohs(lp&65535);key=(pid,local,localport,remote,port,state)
     if key in samples:samples[key]['last_epoch']=now
     else:samples[key]={'pid':pid,'local_ip':local,'local_port':localport,'remote_ip':remote,'remote_port':port,'state':state,'first_epoch':now,'last_epoch':now}
  except Exception as e:monitor_errors.append(repr(e))
  finish.wait(.02)
local=urllib.request.build_opener(urllib.request.ProxyHandler({}));children=[]
report={'sha':'f70f2e4476b4ae7b58d1275615b9d4cd6d725ce2','fixed_ip':IP,'dns_resolution':resolved,'forecast_url':url,'tls_verified':True,'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'source_ca_sha256':hashlib.sha256(pathlib.Path(certifi.where()).read_bytes()).hexdigest(),'bundled_ca_sha256':hashlib.sha256((exe.parent/'_internal/certifi/cacert.pem').read_bytes()).hexdigest(),'curl_version':subprocess.check_output([curl,'--version'],text=True),'trials':[]}
log=(out/'binary.log').open('w',encoding='utf-8')
try:
 data=pathlib.Path(os.environ['ASTROPILOT_DATA_DIR']);(data/'user_profile.json').write_text(json.dumps({'location':{'name':'Synthetic Madrid capture','latitude':40.4,'longitude':-3.7},'preferences':{'bortle':4},'active_equipment':'samyang_183','available_equipment':['samyang_183'],'projects':{},'sessions':[],'profile_revision':1}),encoding='utf-8')
 with socket.socket() as s:s.bind(('127.0.0.1',8000))
 child=subprocess.Popen([str(exe)],cwd=root,env=os.environ.copy(),stdout=log,stderr=log);children.append(child)
 for _ in range(120):
  try:
   identity=json.load(local.open('http://127.0.0.1:8000/v1/runtime-identity',timeout=2));assert identity['build']=='f70f2e4';report['runtime_identity']=identity;break
  except Exception:assert child.poll() is None;time.sleep(.5)
 else:raise RuntimeError('binary_not_ready')
 thread=threading.Thread(target=monitor);thread.start()
 def binary_trial():
  start=time.time();req=urllib.request.Request('http://127.0.0.1:8000/v1/tonight',data=json.dumps({'availability':{'mode':'all_night'}}).encode(),headers={'Content-Type':'application/json'})
  try:
   with local.open(req,timeout=180) as r:status,payload=r.status,json.load(r)
  except urllib.error.HTTPError as e:status,payload=e.code,json.loads(e.read())
  return {'client':'binary','pid':child.pid,'start_epoch':start,'end_epoch':time.time(),'http':status,'status':payload.get('status'),'detail':payload.get('detail'),'creation_refusal':payload.get('creation_refusal')}
 def requests_trial():
  start=time.time();c=subprocess.Popen([sys.executable,str(requests_worker),url],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);children.append(c);stdout,stderr=c.communicate(timeout=45);result=json.loads(stdout);result.update(client='requests',spawn_epoch=start,exit=c.returncode,stderr=stderr[:1000]);return result
 def curl_trial(n):
  start=time.time();c=subprocess.Popen([curl,'--ipv4','--resolve',f'api.open-meteo.com:443:{IP}','--silent','--show-error','--connect-timeout','15','--max-time','30','--output',str(out/f'curl-{n}.body'),'--write-out','%{json}',url],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);children.append(c);stdout,stderr=c.communicate(timeout=45)
  return {'client':'curl','pid':c.pid,'start_epoch':start,'end_epoch':time.time(),'exit':c.returncode,'stderr':stderr[:1500],'metrics':json.loads(stdout)}
 start_epoch=float(os.environ['TRIAL_START_EPOCH'])
 for n in range(1,9):
  target=start_epoch+(n-1)*30
  while time.time()<target:time.sleep(min(.2,target-time.time()))
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   fs=[pool.submit(binary_trial),pool.submit(requests_trial),pool.submit(curl_trial,n)];results=[f.result() for f in fs]
  for result in results:result['round']=n
  report['trials'].extend(results);report['tcp_owner_samples']=list(samples.values());(out/'comparison.json').write_text(json.dumps(report,indent=2));print('round',n,json.dumps(results),flush=True);time.sleep(3)
except Exception as e:report['error']=repr(e);raise
finally:
 finish.set()
 if 'thread' in locals():thread.join(timeout=10)
 for c in children:
  if c.poll() is None:c.terminate();c.wait(timeout=20)
 log.close();report['tcp_owner_samples']=list(samples.values());report['tcp_monitor_errors']=monitor_errors;report['children_reaped']=all(c.poll() is not None for c in children);(out/'comparison.json').write_text(json.dumps(report,indent=2))
