"""Run only public synthetic tests with independent per-run directories."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET

SOURCE = Path(os.environ['PRODUCT_SOURCE']).resolve()
OUT = Path(os.environ['HTTPX_PROOF']).resolve()
OUT.mkdir(parents=True, exist_ok=False)
TOOLS = Path(__file__).resolve().parent
expected = '40a2d333378486319eb279bc456884d5f5f17e4d'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip() == expected
assert importlib.metadata.version('httpx2') == importlib.metadata.version('httpcore2') == '2.13.1'
lock = tomllib.loads((SOURCE / 'uv.lock').read_text())
packages = {p['name']: p for p in lock['package']}
pending = ['astropilot']
production = set()
while pending:
    name = pending.pop()
    if name not in production:
        production.add(name)
        pending.extend(p['name'] for p in packages[name].get('dependencies', []))
assert 'httpx2' not in production and 'httpcore2' not in production
assert any(p['name'] == 'httpx2' for p in packages['astropilot']['optional-dependencies']['test'])
env = {k: v for k, v in os.environ.items() if not k.startswith(('ASTROPILOT_', 'NIGHTMERIT_', 'FIELD_LAB_'))}
for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TMP', 'TEMP', 'TMPDIR',
            'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'ASTROPILOT_DATA_DIR'):
    p = OUT / 'environment' / key
    p.mkdir(parents=True)
    env[key] = str(p)
env['PYTHONUTF8'] = '1'
if os.environ.get('NODE_BINARY'):
    env['PATH'] = str(Path(os.environ['NODE_BINARY']).parent) + os.pathsep + env['PATH']
selected = [
    'tests/api/test_execution_session_api.py', 'tests/api/test_execution_session_ui.py',
    'tests/api/test_project_progress_restore_consistency.py',
    'tests/api/test_intent_progress_persistence_diagnostics.py',
    'tests/services/test_intent_progress_credit.py',
    'tests/guardian/test_guardian_http_transport.py',
    'tests/architecture/test_runtime_launcher.py',
    str(TOOLS / 'test_transport.py'),
]
with (OUT / 'tests.log').open('wb') as log:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', *selected,
                             '--junitxml=' + str(OUT / 'tests.xml')], cwd=SOURCE, env=env,
                            stdout=log, stderr=subprocess.STDOUT, timeout=240)
assert result.returncode == 0, (OUT / 'tests.log').read_text(encoding='utf-8')[-6000:]
cases = ET.parse(OUT / 'tests.xml')
assert not cases.findall('.//skipped') and not cases.findall('.//failure') and not cases.findall('.//error')
result = {'result': 'PASS', 'source_sha': expected, 'httpx2': '2.13.1', 'httpcore2': '2.13.1',
          'tests': len(cases.findall('.//testcase')), 'production_dependency_closure': sorted(production),
          'test_extra_only': True, 'loopback_http_only': True, 'physical_user_test': False,
          'uv_lock_sha256': hashlib.sha256((SOURCE / 'uv.lock').read_bytes()).hexdigest()}
(OUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
