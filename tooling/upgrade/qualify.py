"""Real installed frozen runtimes, isolated profiles; no user installation touched."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

SOURCE=Path(os.environ['PRODUCT_SOURCE']).resolve()
SHA='ee5df1456d0a60e9149ae792efc601e8e57f7c68'
WINDOWS=os.name=='nt'
OUT=Path(os.environ['UPGRADE_PROOF']).resolve()
CURRENT=Path(os.environ['CURRENT_CANDIDATE']).resolve()
LEGACY=Path(os.environ['LEGACY_CANDIDATE']).resolve()
MODERN=Path(os.environ['MODERN_CANDIDATE']).resolve()
MODERN_SHA=os.environ['MODERN_SHA']
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))
ROWS=[]

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

def payload_root():return Path(os.environ['CURRENT_PAYLOAD']).resolve()

def install(candidate,case,upgrade=False):
    target=case/'Applications'/('AstroPilot' if WINDOWS else 'AstroPilot.app')
    target.parent.mkdir(exist_ok=True)
    if WINDOWS:
        args=[str(candidate),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS','/TASKS=',f'/LOG={case / ("upgrade.log" if upgrade else "install.log")}']
        if not upgrade:args.append('/DIR='+str(target))
        # For upgrade, omit /DIR to exercise the installer's previous-app-directory contract.
        r=subprocess.run(args,env=environment(case),timeout=240)
        assert r.returncode==0,('installer exit',r.returncode)
        exe=target/'AstroPilot.exe'
    else:
        stage=case/'Applications'/'incoming.app'
        subprocess.run(['/usr/bin/ditto',str(candidate),str(stage)],check=True,timeout=180)
        if target.exists():target.rename(case/'previous-bundle.app')
        stage.rename(target)
        exe=target/'Contents/MacOS/AstroPilot'
    assert exe.is_file(),('installed executable missing',exe)
    if upgrade:
        expected=bundle_inventory(payload_root())
        actual=bundle_inventory(target)
        assert all(actual.get(k)==v for k,v in expected.items()),'Installed payload differs from candidate'
        extras=sorted(set(actual)-set(expected))
        if WINDOWS:
            # Inno's own uninstall metadata is expected. Other residue is reported.
            residue=[x for x in extras if not Path(x).name.startswith('unins')]
        else: residue=extras;assert not residue,residue
        ROWS.append({'step':case.name+' installed current','payload_matches':True,'extra_payload_files':residue,
                     'previous_app_dir_without_override':WINDOWS})
    return exe

def check_assets():
    for asset in ('index.html','app.js','styles.css','help.js','alert-status.js'):
        expected=(SOURCE/'astropilot/web'/asset).read_bytes()
        if asset=='index.html':expected=expected.decode().replace('__ASTROPILOT_ASSET_TOKEN__','1.0.0b8-'+SHA[:7]).replace('__ASTROPILOT_SESSION_TIMING__','').encode()
        with OPENER.open('http://127.0.0.1:8000'+('/' if asset=='index.html' else '/ui/'+asset),timeout=20) as r:
            assert r.read()==expected,asset

def seed_modern(case):
    env=environment(case);env['PRODUCT_SOURCE']=str(SOURCE)
    r=subprocess.run([sys.executable,str(Path(__file__).with_name('session_seed.py')),str(case/'data'),json.dumps({'method':'INIT'})],
        cwd=SOURCE,env=env,capture_output=True,text=True,timeout=120)
    assert r.returncode==0,(r.stdout,r.stderr)

def credit(label):
    revision=json.loads((ACTIVE/'data/user_profile.json').read_text(encoding='utf-8'))['profile_revision']
    return request('POST','/v1/executions/upgrade-execution-'+label+'/intent-progress-credit',
        {'expected_revision':revision,'evidence_ids':['upgrade-evidence-'+label],'confirm_historical_baseline':label=='ha'})

def create_credits():
    for label,seconds in [('ha',1800),('oiii',900)]:
        eid='upgrade-execution-'+label;mid='qualification-mission-'+label
        request('POST','/v1/executions',{'execution_id':eid,'mission_id':mid})
        body={'execution_id':eid,'mission_id':mid,'status':'in_progress','actual_start':'2026-10-15T20:00:00+00:00','actual_end':None,'actual_duration':None}
        request('POST','/v1/execution-transitions',body)
        body.update(status='completed',actual_end='2026-10-15T21:00:00+00:00',actual_duration=3600)
        request('POST','/v1/execution-transitions',body)
        request('POST','/v1/outcome-evidence',{'evidence_id':'upgrade-evidence-'+label,'execution_id':eid,'category':'acquisition',
            'observed_at':'2026-10-15T21:00:00+00:00','source':'user','usable_integration_duration':seconds})
        assert credit(label)['status']=='applied'

def check_credits():
    p=request('GET','/v1/projects/Sh2-129/progress')
    totals={x['acquisition_intent_id']:x['effective_total_seconds'] for x in p['intent_progress_breakdown']}
    assert totals=={'sh2-129_ha':5400,'ou4_oiii':900},totals
    for label,total in [('ha',5400),('oiii',900)]:
        state=request('GET','/v1/executions/upgrade-execution-'+label+'/session')
        assert state['acquired_after_seconds']==total
        for _ in range(3):assert credit(label)['status']=='already_applied'
    return totals

def main():
    global ACTIVE
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==SHA
    OUT.mkdir(parents=True,exist_ok=False)
    for label,old,oldsha,oldversion in [('legacy',LEGACY,'c47b2e6','1.0.0b7'),('modern',MODERN,MODERN_SHA,'1.0.0b8')]:
        case=OUT/label;case.mkdir();(case/'QUALIFICATION_ONLY').write_text('PUBLIC SYNTHETIC UPGRADE ONLY');(case/'data').mkdir();ACTIVE=case
        if label=='modern':seed_modern(case)
        exe=install(old,case)
        with Server(exe,case,oldsha,oldversion) as oldserver:
            if label=='legacy':
                request('PUT','/v1/configuration',{'site':{'name':'UPGRADE TEST ONLY','latitude':46.9,'longitude':6.6,'bortle':4},
                    'equipment':{'preset_id':'samyang_183'},'projects':{'Sh2-129':{'hours':2,'target_hours':20,'importance':9}}})
                oldconfig=request('GET','/v1/configuration')
            else:create_credits();check_credits()
            oldidentity=oldserver.identity
        # Freeze all old logical authority files after the old runtime is stopped.
        before=authority(case/'data');frozen=case/'frozen-before-upgrade';shutil.copytree(case/'data',frozen)
        expected_profile=(case/'data/user_profile.json').read_bytes()
        exe=install(CURRENT,case,upgrade=True)
        assert authority(case/'data')==before,'Installer changed logical data'
        for boot in range(2):
            with Server(exe,case,SHA,'1.0.0b8') as current:
                check_assets()
                if label=='legacy':
                    config=request('GET','/v1/configuration')
                    assert config['projects']==oldconfig['projects'],(config['projects'],oldconfig['projects'])
                else:totals=check_credits()
                identity=current.identity
            assert (case/'data/user_profile.json').read_bytes()==expected_profile,'Read/replay changed profile'
            assert authority(case/'data')==before,'Read/replay changed logical authority'
        assert authority(frozen)==before
        ROWS.append({'step':label+' upgrade','result':'PASS','old_identity':oldidentity,'new_identity':identity,
            'old_authority_sha256':before,'after_authority_sha256':authority(case/'data'),'frozen_source_unchanged':True,
            'restart':True,'replay':'already_applied' if label=='modern' else 'not_applicable_no_credit_in_legacy',
            'ha_seconds':5400 if label=='modern' else None,'oiii_seconds':900 if label=='modern' else None})
    # Read error added by #385 must also exist inside the actual current frozen payload.
    fault=OUT/'fault';fault.mkdir();(fault/'QUALIFICATION_ONLY').write_text('PUBLIC SYNTHETIC FAULT COPY');shutil.copytree(OUT/'modern/data',fault/'data');ACTIVE=fault
    baseline=authority(fault/'data');bad=fault/'data/execution_lineage/.json';bad.write_text('{',encoding='utf-8')
    with Server(exe,fault,SHA,'1.0.0b8'):
        refused=request('GET','/v1/execution-sessions',expected=503)
        assert refused['detail']['code']=='invalid_json_document',refused
    bad.unlink()
    with Server(exe,fault,SHA,'1.0.0b8'):check_credits()
    assert authority(fault/'data')==baseline
    proof={'result':'PASS','product_sha':SHA,'os':platform.platform(),'rows':ROWS,'fault_read_refused_and_recovered':True,
        'real_frozen_runtime':True,'isolated_profile':True,'real_user_profile_used':False,'physical_user_pc':False,
        'desktop_ui_observed':False,'port_released':True,'new_credit_after_upgrade':False,
        'windows_registry_changes_only_disposable_runner':WINDOWS}
    (OUT/'upgrade-qualification.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in proof.items() if k!='rows'}))

if __name__=='__main__':main()
