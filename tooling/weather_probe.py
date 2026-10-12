"""Read-only probe of the exact source HTTP worker, with external phase telemetry."""
import argparse,hashlib,importlib.util,json,pathlib,socket,sys,time
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--connect-ip',choices=['188.40.99.226','94.130.142.35']);a=p.parse_args()
source=pathlib.Path(a.source);spec=importlib.util.spec_from_file_location('exact_weather_worker',source/'astropilot/guardian_http_worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
result={'phase':'tls_context','timings':{},'dns':[],'success':False,'ca_sha256':hashlib.sha256(pathlib.Path(worker.certifi.where()).read_bytes()).hexdigest()};began=time.monotonic()
old_dns=socket.getaddrinfo
old_connect=socket.create_connection
class Connection(worker.HTTPSConnection):
 def connect(self):
  result['hostname']=self.host;result['connect_ip']=a.connect_ip;result['tls_verification']={'verify_mode':int(self._context.verify_mode),'check_hostname':self._context.check_hostname};assert self.host=='api.open-meteo.com' and self._context.check_hostname and int(self._context.verify_mode)==2
  result['phase']='connect';t=time.monotonic()
  try:super().connect()
  finally:result['timings']['connection_including_tls']=time.monotonic()-t
  result['tls']={'version':self.sock.version(),'cipher':self.sock.cipher()[0],'issuer':self.sock.getpeercert().get('issuer')};result['phase']='request'
 def getresponse(self):
  result['phase']='response_headers';t=time.monotonic()
  try:r=super().getresponse()
  finally:result['timings']['response_headers']=time.monotonic()-t
  result['http_status']=r.status;result['response_headers']={key:r.getheader(key) for key in ['Server','Retry-After','Content-Type','Content-Length']}
  result['phase']='response_body'
  if r.status!=200:result['error_response_excerpt']=r.read(512).decode('utf-8',errors='replace')
  return r
def dns(*args,**kwargs):
 result['phase']='dns';t=time.monotonic()
 try:
  if a.connect_ip and args[0]=='api.open-meteo.com':args=(a.connect_ip,)+args[1:]
  r=old_dns(*args,**kwargs)
 finally:result['timings']['dns']=time.monotonic()-t
 result['dns']=[{'family':v[0],'address':v[4][0]} for v in r];result['phase']='tcp';return r
def tcp(*args,**kwargs):
 result['phase']='tcp';t=time.monotonic()
 try:r=old_connect(*args,**kwargs)
 finally:result['timings']['tcp_including_dns']=time.monotonic()-t
 result['peer']=r.getpeername();result['phase']='tls_handshake';return r
worker.HTTPSConnection=Connection;socket.getaddrinfo=dns;socket.create_connection=tcp
try:
 body=worker.request(40.4,-3.7,15);payload=json.loads(body);assert isinstance(payload.get('current'),dict);result.update(success=True,body_bytes=len(body),phase='completed')
except Exception as error:result.update(error_type=type(error).__name__,error_message=str(error)[:250])
finally:
 result['elapsed_seconds']=time.monotonic()-began;pathlib.Path(a.out).write_text(json.dumps(result,indent=2));print(json.dumps(result))
