"""Local-only CONNECT/TLS fixture, never an Internet proxy."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import socketserver
import ssl
import threading
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, reset_tzpath

MODES = ('connection_error','tls_error','read_timeout','http_429','http_503','success')


def _length(size):
    if size < 128:
        return bytes([size])
    value=size.to_bytes((size.bit_length()+7)//8,'big')
    return bytes([128+len(value)])+value


def _integer(value):
    value=value.lstrip(b'\0') or b'\0'
    if value[0]&128: value=b'\0'+value
    return b'\x02'+_length(len(value))+value


def _pem(label, data):
    encoded=base64.b64encode(data).decode('ascii')
    return '-----BEGIN '+label+'-----\n'+'\n'.join(encoded[i:i+64] for i in range(0,len(encoded),64))+'\n-----END '+label+'-----\n'


def prepare_certificates(directory):
    directory=Path(directory)
    for name in ('valid','wrong'):
        source=directory/(name+'.json')
        document=json.loads(source.read_text(encoding='utf-8-sig'))
        cert=base64.b64decode(document['certificate'],validate=True)
        body=_integer(b'\0')+b''.join(_integer(base64.b64decode(document[field],validate=True))
            for field in ('Modulus','Exponent','D','P','Q','DP','DQ','InverseQ'))
        key=b'\x30'+_length(len(body))+body
        (directory/(name+'.pem')).write_text(_pem('CERTIFICATE',cert),encoding='ascii')
        (directory/(name+'-key.pem')).write_text(_pem('RSA PRIVATE KEY',key),encoding='ascii')
        source.unlink()
    (directory/'trust.pem').write_text(''.join((directory/(n+'.pem')).read_text() for n in ('valid','wrong')),encoding='ascii')


def payload_for(path):
    parts=urlsplit(path)
    if parts.path!='/v1/forecast': raise ValueError('unexpected_fixture_path')
    params=parse_qs(parts.query,strict_parsing=True)
    latitude=float(params['latitude'][0]);longitude=float(params['longitude'][0])
    zone=ZoneInfo(params['timezone'][0]);now=datetime.now(zone)
    start=int(now.replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
    units={'cloud_cover':'%','cloud_cover_low':'%','cloud_cover_mid':'%',
        'cloud_cover_high':'%','precipitation':'mm','relative_humidity_2m':'%',
        'visibility':'m','wind_speed_10m':'km/h','temperature_2m':'°C'}
    values={'cloud_cover':0,'cloud_cover_low':0,'cloud_cover_mid':0,'cloud_cover_high':0,
        'precipitation':0,'relative_humidity_2m':65,'visibility':24000,
        'wind_speed_10m':5,'temperature_2m':12}
    return {'latitude':latitude,'longitude':longitude,'elevation':800,
        'timezone':params['timezone'][0],'utc_offset_seconds':int(now.utcoffset().total_seconds()),
        'hourly_units':{'time':'unixtime',**units},
        'hourly':{'time':[start+i*3600 for i in range(168)],
            **{key:[value]*168 for key,value in values.items()}}}


def _headers(connection):
    data=b''
    while b'\r\n\r\n' not in data:
        chunk=connection.recv(4096)
        if not chunk: raise ConnectionError('fixture_client_closed')
        data+=chunk
        if len(data)>65536: raise ValueError('fixture_headers_too_large')
    return data.split(b'\r\n',1)[0].decode('ascii')


class WeatherFixture:
    def __init__(self, certificates, tzdata_path, mode):
        if mode not in MODES: raise ValueError('fixture_mode_invalid')
        reset_tzpath([str(tzdata_path)])
        self.mode=mode;self.records=[];self.errors=[];self.lock=threading.Lock()
        self.stopping=threading.Event();self.connections=set()
        self.contexts={}
        for name in ('valid','wrong'):
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(Path(certificates)/(name+'.pem')),str(Path(certificates)/(name+'-key.pem')))
            self.contexts[name]=context
        fixture=self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self): fixture._handle(self.request)
        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address=False
            daemon_threads=True
            block_on_close=False
        self.server=Server(('127.0.0.1',0),Handler)
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.1},daemon=True)
        self.thread.start()

    def _handle(self, connection):
        with self.lock: self.connections.add(connection)
        connection.settimeout(5)
        tls=None;mode=None
        try:
            line=_headers(connection)
            if line!='CONNECT api.open-meteo.com:443 HTTP/1.0' and line!='CONNECT api.open-meteo.com:443 HTTP/1.1':
                raise ValueError('fixture_unexpected_destination')
            with self.lock:
                mode=self.mode
                self.records.append({'mode':mode,'simulated':True})
            if mode=='connection_error':
                connection.sendall(b'HTTP/1.1 502 Simulated transport refusal\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                return
            connection.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
            context=self.contexts['wrong' if mode=='tls_error' else 'valid']
            tls=context.wrap_socket(connection,server_side=True)
            with self.lock: self.connections.add(tls)
            line=_headers(tls)
            method,path,version=line.split(' ',2)
            if method!='GET': raise ValueError('fixture_unexpected_method')
            if mode=='read_timeout':
                self.stopping.wait(20)
                return
            status=429 if mode=='http_429' else 503 if mode=='http_503' else 200
            body=json.dumps(payload_for(path) if status==200 else {'error':True,'reason':'simulated_test_only'},ensure_ascii=False).encode('utf-8')
            tls.sendall(('HTTP/1.1 '+str(status)+' Simulated\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body))+'\r\nConnection: close\r\n\r\n').encode('ascii')+body)
        except (ssl.SSLError,ConnectionError,OSError,ValueError) as error:
            if mode not in ('tls_error','read_timeout') and not self.stopping.is_set():
                with self.lock: self.errors.append(type(error).__name__)
        finally:
            for item in (tls,connection):
                if item is not None:
                    try: item.close()
                    except OSError: pass
                    with self.lock: self.connections.discard(item)

    def recover(self):
        with self.lock: self.mode='success'

    def close(self):
        self.stopping.set();self.server.shutdown();self.server.server_close();self.thread.join(3)
        with self.lock: connections=list(self.connections)
        for connection in connections:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            try: connection.close()
            except OSError: pass
        return not self.thread.is_alive()
