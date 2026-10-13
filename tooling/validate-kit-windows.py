"""Native kit qualification with synthetic inputs, never a real user profile."""
import builtins
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


assert sys.platform == 'win32'
ROOT = Path(__file__).resolve().parent
WORK = Path(os.environ['RUNNER_TEMP'])/'pr376-kit-qualification'
WORK.mkdir()
sys.path.insert(0, str(ROOT))
from windows_job import IsolatedProcess
from kit_safety import safe_extract


SERVER = r'''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json, os, pathlib, sys
root=pathlib.Path.cwd()
class Handler(BaseHTTPRequestHandler):
 def log_message(self, *args): pass
 def reply(self, body):
  data=json.dumps(body).encode(); self.send_response(200)
  self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data)))
  self.end_headers(); self.wfile.write(data)
 def do_GET(self):
  self.reply({'application':'astropilot','build':'a6f5bd8','version':'1.0.0b8'})
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  with (root/'requests.log').open('a') as f: f.write(self.path+'\n')
  case=root.parent.name
  data_dir=pathlib.Path(os.environ['ASTROPILOT_DATA_DIR'])
  assert data_dir == root/'data'
  (data_dir/'fixture-write.json').write_text('{}')
  if self.path=='/v1/tonight':
   day=data['availability']['start_local'][:10]
   body={'night_date':('2026-10-13' if case=='wrong-night' else day),'decision_id':'fixture-decision',
     'catalog_key':'Sh2-129','acquisition_intent_choice_available':True,
     'viable_acquisition_intent_ids':(['sh2-129_ha','ou4_oiii'] if case!='refused' else []),
     'acquisition_intent_assessments':[]}
   self.reply(body)
  elif self.path=='/v1/decision-selections':
   intent=data['acquisition_intent_id']
   filt='Ha' if intent=='sh2-129_ha' else 'OIII'
   if case=='wrong-filter': filt='L'
   self.reply({'status':'accepted','selected_acquisition_intent_id':intent,
     'mission':{'acquisition_intent_id':intent,'selected_filter':{'filter_type':filt}}})
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
for name in ('../escape.txt', '/escape.txt', 'C:/escape.txt', 'a\\escape.txt'):
    z = WORK/(hashlib.sha256(name.encode()).hexdigest()+'.zip')
    with zipfile.ZipFile(z,'w') as bundle:
        bundle.writestr(name,'fixture')
    try:
        safe_extract(z, WORK/(z.stem+'-extracted'))
    except RuntimeError:
        pass
    else:
        raise AssertionError('Unsafe ZIP accepted')
findings.append({'check':'archive_path_refusal','passed':True})

for scenario, expected in [('good','PASS'), ('wrong-night','FAIL'),
                           ('wrong-filter','FAIL'), ('refused','NOT_VALIDATED')]:
    kit = WORK/scenario
    kit.mkdir()
    for name in ('test-choix.py','windows_job.py','kit_safety.py'):
        shutil.copy2(ROOT/name, kit/name)
    cfg = kit/'Configuration-Mac-reference.zip'
    with zipfile.ZipFile(cfg,'w') as bundle:
        bundle.writestr('user_profile.json','{"projects":{}}')
    binary = kit/'AstroPilot-PR376-a6f5bd8-portable.zip'
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
    module.IsolatedProcess=launch_with_scenario
    answers=iter(['2026-10-14','20:30','23:00'])
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
    assert report['original_files_unchanged'] is True
    assert all(p.stopped for p in launched)
    assert all(c['binary_stopped'] and c['port_released'] for c in report['cases'])
    assert json.loads((kit/'profil-Mac-reference/user_profile.json').read_text())=={'projects':{}}
    requests=''.join(p.read_text() for p in kit.rglob('requests.log'))
    if scenario in ('wrong-night','refused'):
        assert '/v1/decision-selections' not in requests
    else:
        assert requests.count('/v1/decision-selections')==2
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',8000))
    with zipfile.ZipFile(results[0].parent.with_suffix('.zip')) as bundle:
        assert 'comparison.json' in bundle.namelist()
        assert not any('/data/' in name or name.endswith('user_profile.json') for name in bundle.namelist())
    findings.append({'check':scenario,'passed':True,'reported_result':expected})

# A real unrelated listener is refused before any API POST.
with socket.socket() as listener:
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

report={'passed':True,'platform':sys.platform,'python':sys.version,
        'checks':findings,'profile':'synthetic only','real_user_data_accessed':False}
(WORK/'validation-kit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
