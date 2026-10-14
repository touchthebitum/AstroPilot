"""Native kit qualification with synthetic inputs, never a real user profile."""
import builtins
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
import urllib.request


assert sys.platform == 'win32'
ROOT = Path(__file__).resolve().parent
WORK = Path(os.environ['RUNNER_TEMP'])/'pr376-kit-qualification'
WORK.mkdir()
sys.path.insert(0, str(ROOT))
from windows_job import IsolatedProcess
from kit_safety import safe_extract


SERVER = r'''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json, os, pathlib, sys, datetime
root=pathlib.Path.cwd()
class Handler(BaseHTTPRequestHandler):
 def log_message(self, *args): pass
 def reply(self, body):
  data=json.dumps(body).encode(); self.send_response(200)
  self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data)))
  self.end_headers(); self.wfile.write(data)
 def do_GET(self):
  self.reply({'application':'astropilot','build':'a295134','version':'1.0.0b8'})
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  with (root/'requests.log').open('a') as f: f.write(self.path+'\n')
  case=root.parent.name
  data_dir=pathlib.Path(os.environ['ASTROPILOT_DATA_DIR'])
  assert data_dir == root/'data'
  (data_dir/'fixture-write.json').write_text('{}')
  if self.path=='/v1/tonight':
   start=datetime.datetime.fromisoformat(data['availability']['start_local'])
   day=(start.date()-datetime.timedelta(days=1) if start.hour<12 else start.date()).isoformat()
   body={'night_date':('2026-10-13' if case=='wrong-night' else day),'decision_id':'fixture-decision',
     'catalog_key':'Sh2-129','acquisition_intent_choice_available':True,
     'viable_acquisition_intent_ids':(['sh2-129_ha','ou4_oiii'] if case!='refused' else []),
     'acquisition_intent_assessments':[]}
   if case=='no-night': body['night_date']=None
   self.reply(body)
  elif self.path=='/v1/decision-selections':
   intent=data['acquisition_intent_id']
   filt='Ha' if intent=='sh2-129_ha' else 'OIII'
   if case=='wrong-filter': filt='L'
   selected={'filter_type':filt,'bandwidth_nm':6.5,'source':'authorized_optical_profile'}
   if case=='null-filter': selected=None
   if case=='legacy-source': selected['source']='legacy_inventory'
   if case=='wrong-bandwidth': selected['bandwidth_nm']=7
   self.reply({'status':'accepted','selected_acquisition_intent_id':intent,
     'mission':{'acquisition_intent_id':intent,'selected_filter':selected}})
  else: raise AssertionError('Unexpected mutating endpoint')
HTTPServer(('127.0.0.1',8000),Handler).serve_forever()
'''


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


findings = []
# The native Job contains the child before it can fork; closing kills descendants.
contain = WORK/'containment'
contain.mkdir()
code = ("import subprocess,sys,time,json,pathlib,os; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
        "pathlib.Path('pids.json').write_text(json.dumps([os.getpid(),child.pid])); time.sleep(120)")
child = IsolatedProcess([sys.executable, '-c', code], contain, os.environ.copy())
try:
    for _ in range(100):
        if (contain/'pids.json').exists():
            break
        time.sleep(.1)
    pids = json.loads((contain/'pids.json').read_text())
    assert all(child.owns_pid(pid) for pid in pids)
finally:
    child.close()
assert child.stopped
findings.append({'check':'suspended_launch_and_descendant_cleanup','passed':True})

# Extraction cannot traverse out of the new kit directory.
for name in ('../escape.txt', '/escape.txt', 'C:/escape.txt', 'a/../escape.txt'):
    z = WORK/(hashlib.sha256(name.encode()).hexdigest()+'.zip')
    with zipfile.ZipFile(z,'w') as bundle:
        bundle.writestr(name,'fixture')
    try:
        safe_extract(z, WORK/(z.stem+'-extracted'))
    except RuntimeError:
        pass
    else:
        raise AssertionError('Unsafe ZIP accepted: '+name)
findings.append({'check':'archive_path_refusal','passed':True})

for scenario, expected in [('good','PASS'), ('after-midnight','PASS'), ('invalid-date-retry','PASS'), ('wrong-night','FAIL'),
                           ('wrong-filter','FAIL'), ('null-filter','FAIL'), ('legacy-source','FAIL'), ('wrong-bandwidth','FAIL'), ('refused','NOT_VALIDATED'), ('no-night','NOT_VALIDATED')]:
    kit = WORK/scenario
    kit.mkdir()
    for name in ('test-choix.py','windows_job.py','kit_safety.py'):
        shutil.copy2(ROOT/name, kit/name)
    cfg = kit/'Configuration-Mac-reference.zip'
    with zipfile.ZipFile(cfg,'w') as bundle:
        bundle.writestr('user_profile.json','{"projects":{}}')
    binary = kit/'AstroPilot-PR379-a295134-portable.zip'
    payload=b'synthetic Windows executable placeholder, never executed'
    with zipfile.ZipFile(binary,'w') as bundle:
        bundle.writestr('AstroPilot/AstroPilot.exe',payload)
    manifest={'user_profile.json':hashlib.sha256(b'{"projects":{}}').hexdigest()}
    (kit/'Manifest-configuration-Mac.json').write_text(json.dumps(manifest))
    (kit/'Kit-provenance.json').write_text(json.dumps({
        'portable_zip_sha256':digest(binary),'mac_reference_zip_sha256':digest(cfg),
        'binary_sha256':hashlib.sha256(payload).hexdigest()}))
    fixture = kit/'fixture_server.py'
    fixture.write_text(SERVER)
    spec=importlib.util.spec_from_file_location('kit_'+scenario.replace('-','_'),kit/'test-choix.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    launched=[]
    def launch(argv, cwd, env):
        process=IsolatedProcess([sys.executable,str(fixture)],cwd,env)
        launched.append(process)
        return process
    module.IsolatedProcess=launch
    # Root.parent is the timestamped result directory; tell the fixture scenario
    # via the environment so the live native harness still uses its own layout.
    original_launch=launch
    def launch_with_scenario(argv,cwd,env):
        env['KIT_FIXTURE_SCENARIO']=scenario
        return original_launch(argv,cwd,env)
    fixture.write_text(SERVER.replace("case=root.parent.name", "case=os.environ['KIT_FIXTURE_SCENARIO']"))
    launch_with_scenario.listening_pids=IsolatedProcess.listening_pids
    module.IsolatedProcess=launch_with_scenario
    answers=iter(['2026-10-16','02:45','04:15'] if scenario=='after-midnight' else
                 ['12026-10-16','02:45','04:15','2026-10-14','20:30','23:00'] if scenario=='invalid-date-retry' else
                 ['2026-10-14','20:30','23:00'])
    original_input=builtins.input
    builtins.input=lambda prompt:next(answers)
    try:
        module.main()
    finally:
        builtins.input=original_input
    results=list(kit.glob('resultats-choix-*/comparison.json'))
    assert len(results)==1
    report=json.loads(results[0].read_text())
    assert report['overall_result']==expected, report
    if scenario=='after-midnight':
        assert all(c['requested_night']=='2026-10-15' for c in report['cases'])
    assert report['original_files_unchanged'] is True
    assert all(p.stopped for p in launched)
    assert all(c['binary_stopped'] and c['port_released'] for c in report['cases'])
    assert json.loads((kit/'profil-Mac-reference/user_profile.json').read_text())=={'projects':{}}
    requests=''.join(p.read_text() for p in kit.rglob('requests.log'))
    if scenario in ('wrong-night','refused','no-night'):
        assert '/v1/decision-selections' not in requests
    else:
        assert requests.count('/v1/decision-selections')==2
    assert not IsolatedProcess.listening_pids()
    with zipfile.ZipFile(results[0].parent.with_suffix('.zip')) as bundle:
        assert 'comparison.json' in bundle.namelist()
        assert not any('/data/' in name or name.endswith('user_profile.json') for name in bundle.namelist())
    findings.append({'check':scenario,'passed':True,'reported_result':expected})

# A real unrelated listener is refused before any API POST.
with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('127.0.0.1',8000))
    listener.listen()
    child=IsolatedProcess([sys.executable,'-c','import time; time.sleep(60)'],WORK,os.environ.copy())
    try:
        try:
            child.listener_pid()
        except RuntimeError as exc:
            assert 'autre processus' in str(exc)
        else:
            raise AssertionError('Unrelated listener accepted')
    finally:
        child.close()
findings.append({'check':'unrelated_server_refused','passed':True})

if os.environ.get('PR376_ARCHIVE_ROOT'):
    archive=next(Path(os.environ['PR376_ARCHIVE_ROOT']).rglob('AstroPilot-1.0.0b8-windows-x86_64-portable.zip'))
    assert digest(archive)==os.environ['KIT_EXPECTED_PORTABLE_SHA']
    smoke=WORK/'real-binary-smoke'
    smoke.mkdir()
    extracted=smoke/'extracted'
    safe_extract(archive,extracted)
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(('ASTROPILOT_','NIGHTMERIT_'))}
    for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','ASTROPILOT_DATA_DIR'):
        directory=smoke/key
        directory.mkdir()
        env[key]=str(directory)
    (Path(env['ASTROPILOT_DATA_DIR'])/'user_profile.json').write_text(json.dumps({
        'location':{'name':'Synthetic validation Madrid','latitude':40.4,'longitude':-3.7},
        'preferences':{'bortle':4},'active_equipment':'samyang_183',
        'available_equipment':['samyang_183'],'projects':{},'sessions':[],'profile_revision':1}))
    noop=smoke/'browser-noop.py'
    noop.write_text('pass\n')
    env['BROWSER']='"'+sys.executable+'" "'+str(noop)+'" %s'
    child=IsolatedProcess([str(extracted/'AstroPilot/AstroPilot.exe')],smoke,env)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            assert child.poll() is None, 'Real executable exited during startup'
            if child.listener_pid() is not None:
                with opener.open('http://127.0.0.1:8000/v1/runtime-identity',timeout=5) as response:
                    identity=json.load(response)
                break
            time.sleep(.2)
        else:
            raise AssertionError('Real executable did not become ready')
        assert identity['build']=='a295134' and identity['version']=='1.0.0b8'
        with opener.open('http://127.0.0.1:8000/',timeout=5) as response:
            assert response.status==200
    finally:
        child.close()
    deadline=time.monotonic()+5
    while IsolatedProcess.listening_pids() and time.monotonic()<deadline:
        time.sleep(.1)
    assert child.stopped and not IsolatedProcess.listening_pids()
    findings.append({'check':'exact_real_binary_with_shipped_job_launcher','passed':True,
                     'identity':identity,'only_GET_requests':True})

report={'passed':True,'platform':sys.platform,'python':sys.version,
        'checks':findings,'profile':'synthetic only','real_user_data_accessed':False}
(WORK/'validation-kit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
