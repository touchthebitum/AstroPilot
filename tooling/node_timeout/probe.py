"""Bounded public-fixture diagnosis; stdlib only before product subprocesses."""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time

SHA = '2fb3cb4d7fb7f391439a86cd09b6019148126643'
SOURCE = Path('candidate').resolve()
OUT = Path(os.environ['RUNNER_TEMP']) / 'node-timeout-proof'
OUT.mkdir()
LAB = Path(os.environ['RUNNER_TEMP']) / 'node-timeout-lab'
LAB.mkdir()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip() == SHA
node = shutil.which('node')
assert node
cold_control = os.environ.get('NODE_COLD_CONTROL') == '1'
base = {k: v for k, v in os.environ.items() if not k.startswith(('ASTROPILOT_', 'NIGHTMERIT_', 'FIELD_LAB_'))}
for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'ASTROPILOT_DATA_DIR', 'TMP', 'TEMP', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME'):
    path = LAB / 'setup' / key
    path.mkdir(parents=True, exist_ok=True)
    base[key] = str(path)
base.update(PYTHONUTF8='1', UV_NO_ENV_FILE='1', UV_PROJECT_ENVIRONMENT=str(LAB / 'venv'),
            UV_CACHE_DIR=str(LAB / 'uv-cache'))
result = {'source_sha': SHA, 'platform': platform.platform(), 'node_path': node,
          'node_version': None if cold_control else subprocess.check_output([node, '--version'], text=True).strip(),
          'protocol': '8 disabled + 3 module + 2 ordered + 1 instrumented seven-state module selection per OS',
          'public_fixtures_only': True, 'rows': [], 'status': 'RUNNING',
          'node_version_invoked_before_tests': not cold_control}

def save():
    (OUT / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

watched = ['tests/architecture/test_opportunity_alert_host_status_integration.py', 'astropilot/web/alert-status.js', 'uv.lock', 'pyproject.toml']
before = {p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in watched}
result['source_hashes_before'] = before
save()
with (OUT / 'sync.log').open('wb') as log:
    subprocess.run(['uv', 'sync', '--locked', '--extra', 'test'], cwd=SOURCE, env=base,
                   stdout=log, stderr=subprocess.STDOUT, timeout=240, check=True)
python = LAB / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
result['python'] = json.loads(subprocess.check_output([str(python), '-c',
    'import sys,json,locale;print(json.dumps({"version":sys.version,"executable":sys.executable,"utf8_mode":sys.flags.utf8_mode,"encoding":locale.getencoding()}))'], env=base, text=True))

module = 'tests/architecture/test_opportunity_alert_host_status_integration.py'
ordered = ['tests/architecture/' + n + '.py' for n in (
    'test_opportunity_alert_windows_task_v1', 'test_opportunity_alert_windows_supervisor_v1',
    'test_opportunity_alert_status_v1', 'test_opportunity_alert_host_status_integration', 'test_opportunity_alert_host_v1')]

def census(case):
    if os.name == 'nt':
        command = ['pwsh', '-NoProfile', '-Command',
          "$x=@(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Select-Object ProcessId,ParentProcessId,CommandLine); ConvertTo-Json -InputObject $x -Compress"]
        raw = subprocess.check_output(command, env=base, text=True, encoding='utf-8', timeout=20)
        rows = json.loads(raw or '[]')
        return [x for x in rows if 'host-status-ui.cjs' in (x.get('CommandLine') or '') and str(case).lower() in x['CommandLine'].lower()]
    raw = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,command='], text=True, timeout=20)
    return [line.strip() for line in raw.splitlines() if 'host-status-ui.cjs' in line and str(case) in line]

phases = [(f'disabled-{i+1:02}', [module + '::test_real_host_snapshot_api_ui[disabled]']) for i in range(8)]
phases += [(f'module-{i+1:02}', [module]) for i in range(3)]
phases += [(f'ordered-{i+1:02}', ordered) for i in range(2)]
phases += [('instrumented-seven-states', [module + '::test_real_host_snapshot_api_ui'])]
if cold_control:
    phases = [('cold-disabled', [module + '::test_real_host_snapshot_api_ui[disabled]'])]
    result['protocol'] = 'one disabled before invoking node version; exit 23 and blocked-child cleanup controls'
for label, tests in phases:
    case = LAB / label
    case.mkdir()
    env = base.copy()
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'ASTROPILOT_DATA_DIR', 'TMP', 'TEMP', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME'):
        p = case / key
        p.mkdir()
        env[key] = str(p)
    args = [str(python), '-m', 'pytest', '-q', '--durations=0',
            '--basetemp=' + str(case / 'pytest'), '--junitxml=' + str(OUT / (label + '.xml'))]
    if label.startswith('instrumented'):
        plugin = Path('operations/tooling/node_timeout').resolve()
        env['PYTHONPATH'] = str(plugin) + os.pathsep + str(SOURCE)
        env['NODE_DIAG_OUT'] = str(OUT / 'instrumented')
        args += ['-p', 'node_probe_plugin']
    args += tests
    start = time.monotonic()
    with (OUT / (label + '.log')).open('wb') as log:
        child = subprocess.Popen(args, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=os.name != 'nt',
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        outer_timeout = False
        try:
            exit_code = child.wait(timeout=240)
        except subprocess.TimeoutExpired:
            outer_timeout = True
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], timeout=20)
            else:
                os.killpg(child.pid, signal.SIGKILL)
            exit_code = child.wait(timeout=20)
    elapsed = time.monotonic() - start
    remaining = census(case)
    row = {'phase': label, 'exit': exit_code, 'elapsed_seconds': elapsed,
           'outer_timeout': outer_timeout, 'remaining_matching_node_processes': remaining}
    result['rows'].append(row)
    save()
    print(json.dumps(row), flush=True)
if cold_control:
    result['node_version'] = subprocess.check_output([node, '--version'], env=base, text=True).strip()
    failure = subprocess.run([node, '-e', 'process.exit(23)'], env=base, capture_output=True, timeout=20)
    assert failure.returncode == 23
    case = LAB / 'blocked-control'
    case.mkdir()
    ready = case / 'ready.json'
    script = case / 'host-status-ui.cjs'
    script.write_text("require('node:fs').writeFileSync(" + json.dumps(str(ready)) +
                      ", JSON.stringify({pid:process.pid}));setInterval(()=>{},1000);", encoding='utf-8')
    with (OUT / 'blocked-control.log').open('wb') as log:
        child = subprocess.Popen([node, str(script)], env=base, stdout=log, stderr=subprocess.STDOUT)
        ready_deadline = time.monotonic() + 20
        observed_timeout = False
        try:
            while not ready.exists() and child.poll() is None and time.monotonic() < ready_deadline:
                time.sleep(0.02)
            assert ready.exists() and child.poll() is None, 'Control did not reach its intentional block'
            assert json.loads(ready.read_text())['pid'] == child.pid
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                observed_timeout = True
            assert observed_timeout, 'Blocked control must time out, not return success'
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
    leftovers = census(case)
    assert child.returncode != 0 and not leftovers
    result['controls'] = {'exit_23_preserved': failure.returncode, 'child_reached_intentional_block': True,
                          'timeout_observed': observed_timeout, 'timeout_seconds': 1,
                          'child_exit_after_kill': child.returncode, 'remaining_matching_node_processes': leftovers,
                          'product_timeout_unchanged_seconds': 20}
result['source_hashes_after'] = {p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in watched}
assert result['source_hashes_after'] == before
result['status'] = 'PASS' if all(x['exit'] == 0 and not x['outer_timeout'] and not x['remaining_matching_node_processes'] for x in result['rows']) else 'OBSERVATION_FAILURE'
save()
if result['status'] != 'PASS':
    raise SystemExit(1)
