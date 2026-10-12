"""Diagnostic-only runtime hook. No validation bypass; write public endpoint telemetry."""
import os,time,json,socket,ssl,http.client,pathlib,sys
root=os.environ.get('WEATHER_DIAGNOSTIC_LOG_DIR')
if root:
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
 path=root/(str(os.getpid())+'.jsonl')
 def event(name,**details):
  with path.open('a',encoding='utf-8') as stream:stream.write(json.dumps({'time':time.time(),'pid':os.getpid(),'event':name,**details})+'\n')
 event('runtime',openssl=ssl.OPENSSL_VERSION,executable=sys.executable)
 original_dns=socket.getaddrinfo;original_tcp=socket.create_connection;original_tls=ssl.SSLContext.wrap_socket;original_response=http.client.HTTPConnection.getresponse
 def dns(*args,**kwargs):
  t=time.monotonic();event('dns_start',host=str(args[0]))
  try:
   result=original_dns(*args,**kwargs);event('dns_ok',seconds=time.monotonic()-t,addresses=[v[4][0] for v in result]);return result
  except Exception as e:event('dns_error',seconds=time.monotonic()-t,error_type=type(e).__name__,message=str(e)[:200]);raise
 def tcp(*args,**kwargs):
  t=time.monotonic();event('tcp_start',destination=str(args[0]))
  try:
   result=original_tcp(*args,**kwargs);event('tcp_ok',seconds=time.monotonic()-t,peer=result.getpeername());return result
  except Exception as e:event('tcp_error',seconds=time.monotonic()-t,error_type=type(e).__name__,message=str(e)[:200]);raise
 def tls(self,*args,**kwargs):
  t=time.monotonic();event('tls_start',hostname=kwargs.get('server_hostname'),verify_mode=int(self.verify_mode),check_hostname=self.check_hostname)
  try:
   result=original_tls(self,*args,**kwargs);event('tls_ok',seconds=time.monotonic()-t,version=result.version(),cipher=result.cipher()[0],issuer=result.getpeercert().get('issuer'));return result
  except Exception as e:event('tls_error',seconds=time.monotonic()-t,error_type=type(e).__name__,message=str(e)[:200]);raise
 def response(self,*args,**kwargs):
  t=time.monotonic();event('http_response_start')
  try:
   result=original_response(self,*args,**kwargs);event('http_response_ok',seconds=time.monotonic()-t,status=result.status,retry_after=result.getheader('Retry-After'));return result
  except Exception as e:event('http_response_error',seconds=time.monotonic()-t,error_type=type(e).__name__,message=str(e)[:200]);raise
 socket.getaddrinfo=dns;socket.create_connection=tcp;ssl.SSLContext.wrap_socket=tls;http.client.HTTPConnection.getresponse=response
