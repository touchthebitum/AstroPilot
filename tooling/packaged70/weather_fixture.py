"""Loopback-only HTTPS forecast fixture. No system trust store is modified."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json,os,shutil,socketserver,ssl,subprocess,tempfile,threading
from urllib.parse import urlsplit,parse_qs

class Forecast:
 def __init__(self,case,zone,lat,lon):
  self.case=case;self.zone=zone;self.lat=float(lat);self.lon=float(lon);self.rows=[]
 def __enter__(self):
  self.temp=tempfile.TemporaryDirectory(prefix='public-weather-tls-',dir=os.environ.get('RUNNER_TEMP'))
  root=Path(self.temp.name);config=root/'fixture.cnf';cert=root/'fixture.crt';key=root/'fixture.key'
  config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=v3\nprompt=no\n[dn]\nCN=api.open-meteo.com\n[v3]\nsubjectAltName=DNS:api.open-meteo.com\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,digitalSignature,keyEncipherment,keyCertSign\nextendedKeyUsage=serverAuth\n',encoding='ascii')
  openssl=shutil.which('openssl') or ('C:/Program Files/Git/usr/bin/openssl.exe' if os.name=='nt' else '/usr/bin/openssl')
  r=subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-nodes','-days','1','-config',str(config),'-keyout',str(key),'-out',str(cert)],capture_output=True,text=True,timeout=30)
  assert r.returncode==0,r.stderr
  context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key);owner=self
  class Handler(socketserver.StreamRequestHandler):
   def handle(self):
    try:
     connect=self.rfile.readline(8192).decode('ascii').strip()
     assert connect=='CONNECT api.open-meteo.com:443 HTTP/1.0' or connect=='CONNECT api.open-meteo.com:443 HTTP/1.1',connect
     while self.rfile.readline(8192) not in (b'\r\n',b'\n',b''):pass
     self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');self.wfile.flush()
     with context.wrap_socket(self.connection,server_side=True) as tls:
      tls.settimeout(20)
      stream=tls.makefile('rb');line=stream.readline(32768).decode('ascii').strip();method,url,version=line.split(' ')
      while stream.readline(8192) not in (b'\r\n',b'\n',b''):pass
      parsed=urlsplit(url);query=parse_qs(parsed.query)
      assert method=='GET' and parsed.path=='/v1/forecast' and not parsed.netloc,line
      assert abs(float(query['latitude'][0])-owner.lat)<1e-6 and abs(float(query['longitude'][0])-owner.lon)<1e-6
      assert query['timezone']==[owner.zone] and query['timeformat']==['unixtime']
      now=datetime.now(timezone.utc);start=now.replace(hour=0,minute=0,second=0,microsecond=0);count=192
      units={'cloud_cover':'%','cloud_cover_low':'%','cloud_cover_mid':'%','cloud_cover_high':'%','precipitation':'mm','relative_humidity_2m':'%','visibility':'m','wind_speed_10m':'km/h','temperature_2m':'°C'}
      values={'cloud_cover':0.,'cloud_cover_low':0.,'cloud_cover_mid':0.,'cloud_cover_high':0.,'precipitation':0.,'relative_humidity_2m':40.,'visibility':40000.,'wind_speed_10m':3.,'temperature_2m':10.}
      payload={'latitude':owner.lat,'longitude':owner.lon,'elevation':837.,'timezone':owner.zone,'utc_offset_seconds':int(now.astimezone(ZoneInfo(owner.zone)).utcoffset().total_seconds()),'hourly_units':{'time':'unixtime',**units},'hourly':{'time':[int((start+timedelta(hours=i)).timestamp()) for i in range(count)],**{k:[v]*count for k,v in values.items()}}}
      data=json.dumps(payload).encode();tls.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data)
      owner.rows.append({'connect':connect,'request':line,'query':query,'tls':tls.version(),'reference':now.isoformat(),'public_synthetic_forecast':True})
    except Exception as e:owner.rows.append({'error':repr(e)})
    finally:(owner.case/'weather-requests.json').write_text(json.dumps(owner.rows,indent=2),encoding='utf-8')
  class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
  self.server=Server(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.config={'HTTPS_PROXY':'http://127.0.0.1:'+str(self.server.server_address[1]),'HTTP_PROXY':'http://127.0.0.1:'+str(self.server.server_address[1]),'NO_PROXY':'127.0.0.1,localhost','REQUESTS_CA_BUNDLE':str(cert)}
  (self.case/'weather-proxy.json').write_text(json.dumps(self.config),encoding='utf-8')
  return self
 def __exit__(self,*args):
  self.server.shutdown();self.server.server_close();self.thread.join(timeout=10);self.temp.cleanup()
  assert not any('error' in r for r in self.rows),self.rows
