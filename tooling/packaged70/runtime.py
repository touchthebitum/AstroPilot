"""Owned frozen listener and disposable environment helpers; no installer or real profile access."""
from pathlib import Path
import hashlib,json,os,socket,subprocess,sys,time,urllib.request,urllib.error
SOURCE=Path(os.environ['PRODUCT_SOURCE']).resolve()
SHA=os.environ['APPROVED_SHA']
WINDOWS=os.name=='nt'
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def authority(root):
    return {p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*.json'))
            if p.is_file() and p.relative_to(root).parts[0]!='Logs'}

def bundle_inventory(root):
    result={}
    for base,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:
            p=Path(base)/name;key=p.relative_to(root).as_posix()
            if p.is_symlink(): result[key]={'link':os.readlink(p)}
            elif p.is_file(): result[key]={'sha256':digest(p)}
    return result

def environment(case):
    env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
    for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME'):
        p=case/'environment'/key;p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
    env['ASTROPILOT_DATA_DIR']=str(case/'data')
    noop=case/'no_browser.py';noop.write_text('pass\n',encoding='utf-8')
    env['BROWSER']=f'"{sys.executable}" "{noop}" %s'
    return env

def request(method,path,body=None,expected=200):
    q=urllib.request.Request('http://127.0.0.1:8000'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json'},method=method)
    try:
        with OPENER.open(q,timeout=20) as r:status=r.status;payload=json.load(r)
    except urllib.error.HTTPError as e:status=e.code;payload=json.load(e)
    assert status==expected,(method,path,status,payload)
    return payload

def listener_owner():
    if WINDOWS:
        command=['powershell','-NoProfile','-Command',"Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"]
    else: command=['/usr/sbin/lsof','-nP','-iTCP:8000','-sTCP:LISTEN','-t']
    r=subprocess.run(command,capture_output=True,text=True,timeout=20)
    return {int(x) for x in r.stdout.split() if x.isdigit()}

class Server:
    def __init__(self,exe,case,build=None,version=None):self.exe=exe;self.case=case;self.build=build;self.version=version;self.child=None
    def __enter__(self):
        assert not listener_owner(), 'A listener already owns port 8000'
        with socket.socket() as s:
            assert s.connect_ex(('127.0.0.1',8000))!=0, 'Port already listening'
        self.stdout=(self.case/'stdout.log').open('ab');self.stderr=(self.case/'stderr.log').open('ab')
        self.child=subprocess.Popen([str(self.exe)],cwd=self.case,env=environment(self.case),stdout=self.stdout,stderr=self.stderr)
        try:
            for _ in range(180):
                assert self.child.poll() is None,('runtime exited',self.exe,self.child.returncode)
                try: identity=request('GET','/v1/runtime-identity')
                except (OSError,urllib.error.URLError): time.sleep(.3);continue
                assert identity['application']=='astropilot',identity
                if self.build:assert identity['build']==self.build[:7],identity
                if self.version:assert identity['version']==self.version,identity
                assert listener_owner()=={self.child.pid},('foreign or indirect listener',listener_owner(),self.child.pid)
                self.identity=identity;return self
            raise AssertionError('Runtime startup timeout')
        except BaseException:self.stop();raise
    def stop(self):
        if self.child and self.child.poll() is None:
            self.child.terminate()
            try:self.child.wait(timeout=30)
            except subprocess.TimeoutExpired:self.child.kill();self.child.wait(timeout=30)
        self.stdout.close();self.stderr.close()
        for _ in range(100):
            with socket.socket() as s: busy=s.connect_ex(('127.0.0.1',8000))==0
            if not busy:return
            time.sleep(.1)
        raise AssertionError('Port not released after stopping own runtime')
    def __exit__(self,*args):self.stop()

def check_assets():
    for asset in ('index.html','app.js','styles.css','help.js','alert-status.js'):
        expected=(SOURCE/'astropilot/web'/asset).read_bytes()
        if asset=='index.html':expected=(SOURCE/'astropilot/web/index.html').read_text(encoding='utf-8').replace('__ASTROPILOT_ASSET_TOKEN__','1.0.0b8-'+SHA[:7]).replace('__ASTROPILOT_SESSION_TIMING__','').encode()
        with OPENER.open('http://127.0.0.1:8000'+('/' if asset=='index.html' else '/ui/'+asset),timeout=20) as r:
            assert r.read()==expected,asset
