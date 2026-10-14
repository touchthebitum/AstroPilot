"""Native coordinator qualification: synthetic worker, real Windows containment."""
import builtins
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import diagnostic_launcher as launcher
from windows_job import IsolatedProcess

assert sys.platform == 'win32'
root = Path(__file__).resolve().parent
profile = b'{"projects":{}}'
with zipfile.ZipFile(root / 'Configuration-Mac-reference.zip', 'w') as bundle:
    bundle.writestr('user_profile.json', profile)
(root / 'Manifest-configuration-Mac.json').write_text(json.dumps({'user_profile.json': hashlib.sha256(profile).hexdigest()}))
(root / 'Kit-provenance.json').write_text(json.dumps({
    'source_sha': 'a29513447355b05cbcceda85a10d6dc1f90da3fb',
    'mac_reference_zip_sha256': hashlib.sha256((root / 'Configuration-Mac-reference.zip').read_bytes()).hexdigest()}))
manifest = json.loads((root / 'Manifest-runtime.json').read_text(encoding='utf-8'))
for name in ('diagnostic_launcher.py', 'diagnostic_worker.py', 'test_choix_helpers.py', 'kit_safety.py', 'windows_job.py'):
    manifest[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
(root / 'Manifest-diagnostic.json').write_text(json.dumps(manifest))
fixture = root / 'synthetic-diagnostic-child.py'
fixture.write_text('''import os,json,pathlib
root=pathlib.Path.cwd()
assert pathlib.Path(os.environ['ASTROPILOT_DATA_DIR']) == root/'data'
assert all(pathlib.Path(os.environ[k]).parent==root for k in ['HOME','APPDATA','LOCALAPPDATA','TEMP'])
(root/'data/fixture-write.json').write_text('{}')
(root/'forecast-raw.json').write_text('{"hourly":{"time":[]}}')
(root/'diagnostic.json').write_text(json.dumps({'status':'NO_TESTABLE_WINDOW','no_confirmation_sent':True}))
(root/'worker.log').write_text('synthetic coordinator qualification')
''', encoding='utf-8')
processes = []


def contained_fixture(argv, cwd, env):
    child = IsolatedProcess([argv[0], '-B', str(fixture)], cwd, env)
    processes.append(child)
    return child


launcher.IsolatedProcess = contained_fixture
original_input = builtins.input
builtins.input = lambda prompt: (dt.date.today() + dt.timedelta(days=1)).isoformat()
try:
    launcher.main()
finally:
    builtins.input = original_input
output = next(root.glob('resultats-diagnostic-*.zip'))
with zipfile.ZipFile(output) as bundle:
    names = bundle.namelist()
    report = json.loads(bundle.read('isolation.json'))
    assert report['reference_files_unchanged'] and report['processes_stopped'] and report['worker_exit'] == 0
    assert 'forecast-raw.json' in names and 'worker.log' in names
    assert not any('data/' in n or n.endswith(('user_profile.json', '.key')) for n in names)
assert processes and all(child.stopped for child in processes)
assert (root / 'profil-Mac-reference/user_profile.json').read_bytes() == profile
print('Coordinator containment, export allowlist and reference preservation: passed.')
