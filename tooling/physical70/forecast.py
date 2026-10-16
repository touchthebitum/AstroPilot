"""Offline public forecast, trusted only by the candidate process; no OS trust changes."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json,socketserver,ssl,threading
from urllib.parse import urlsplit,parse_qs
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

class Forecast:
 def __init__(self,root):
  self.root=root;self.rows=[];self.site=None
 def __enter__(self):
  tlsdir=self.root/'temporary-tls';tlsdir.mkdir(exist_ok=True)
  key=rsa.generate_private_key(public_exponent=65537,key_size=2048);now=datetime.now(timezone.utc)
  name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'api.open-meteo.com')])
  cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=2)).add_extension(x509.SubjectAlternativeName([x509.DNSName('api.open-meteo.com')]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(key,hashes.SHA256()))
  keyfile=tlsdir/'fixture.key';certfile=tlsdir/'fixture.crt'
  keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));keyfile.chmod(0o600)
  certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
  context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certfile,keyfile);owner=self
  class Handler(socketserver.StreamRequestHandler):
   def handle(self):
    try:
     self.connection.settimeout(20)
     connect=self.rfile.readline(8192).decode('ascii').strip()
     if connect not in ('CONNECT api.open-meteo.com:443 HTTP/1.0','CONNECT api.open-meteo.com:443 HTTP/1.1'):raise ValueError('Unexpected proxy destination')
     while self.rfile.readline(8192) not in (b'\r\n',b'\n',b''):pass
     self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');self.wfile.flush()
     with context.wrap_socket(self.connection,server_side=True) as tls:
      stream=tls.makefile('rb');line=stream.readline(32768).decode('ascii').strip();method,url,_=line.split(' ')
      while stream.readline(8192) not in (b'\r\n',b'\n',b''):pass
      parsed=urlsplit(url);q=parse_qs(parsed.query);site=owner.site
      if not site or method!='GET' or parsed.path!='/v1/forecast' or parsed.netloc:raise ValueError('Unexpected forecast request')
      if abs(float(q['latitude'][0])-site['latitude'])>1e-6 or abs(float(q['longitude'][0])-site['longitude'])>1e-6 or q['timezone']!=[site['timezone']]:raise ValueError('Only the public test site is allowed')
      now=datetime.now(timezone.utc);start=now.replace(hour=0,minute=0,second=0,microsecond=0);count=192
      values={'cloud_cover':0.,'cloud_cover_low':0.,'cloud_cover_mid':0.,'cloud_cover_high':0.,'precipitation':0.,'relative_humidity_2m':40.,'visibility':40000.,'wind_speed_10m':3.,'temperature_2m':10.}
      units=dict(zip(values,['%','%','%','%','mm','%','m','km/h','°C']))
      payload={'latitude':site['latitude'],'longitude':site['longitude'],'elevation':837.,'timezone':site['timezone'],'utc_offset_seconds':int(now.astimezone(ZoneInfo(site['timezone'])).utcoffset().total_seconds()),'hourly_units':{'time':'unixtime',**units},'hourly':{'time':[int((start+timedelta(hours=i)).timestamp()) for i in range(count)],**{k:[v]*count for k,v in values.items()}}}
      data=json.dumps(payload).encode();tls.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data)
      owner.rows.append({'at':now.isoformat(),'site':site['timezone'],'tls':tls.version(),'public_simulation':True,'http':200})
    except Exception as e:owner.rows.append({'error':str(e)})
    finally:(owner.root/'weather-log.json').write_text(json.dumps(owner.rows,indent=2),encoding='utf-8')
  class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
  self.server=Server(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  proxy='http://127.0.0.1:'+str(self.server.server_address[1]);self.env={'HTTPS_PROXY':proxy,'HTTP_PROXY':proxy,'NO_PROXY':'127.0.0.1,localhost','REQUESTS_CA_BUNDLE':str(certfile)}
  return self
 def __exit__(self,*args):
  self.server.shutdown();self.server.server_close();self.thread.join(timeout=10)
  for p in (self.root/'temporary-tls').glob('*'):p.unlink()
