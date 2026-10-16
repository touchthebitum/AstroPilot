"""Three real-browser cases; never import the product in this parent process."""
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
from setup_browser import install

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).parent

def main():
    out = Path(os.environ['NIGHT_CHAIN_PROOF']).resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert len(source_sha) == 40
    browser, provenance = install()
    provenance.update(source_sha=source_sha, pr_head=os.environ.get('NIGHT_CHAIN_PR_HEAD'))
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    rows = []
    for intent in ('sh2-129_ha', 'ou4_oiii', 'site_changed'):
        # The exported proof directory contains reports, never browser/data profiles.
        case = Path(tempfile.mkdtemp(prefix='night-chain-case-', dir=os.environ.get('RUNNER_TEMP')))
        (case / 'QUALIFICATION_ONLY').write_text('PUBLIC FIXTURE ONLY')
        report = out / intent
        report.mkdir()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('ASTROPILOT_', 'NIGHTMERIT_', 'FIELD_LAB_'))}
        env.update(PYTHONUTF8='1', CASE_ROOT=str(case), CASE_PROOF=str(report), UI_INTENT=intent,
                   CHROME_BINARY=str(browser), NIGHT_CHAIN_SOURCE_SHA=source_sha)
        with (report / 'case.log').open('wb') as log:
            child = subprocess.Popen(
                [sys.executable, '-B', str(SCRIPT / 'browser_run.py')],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=os.name != 'nt',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            try:
                code = child.wait(timeout=300)
            finally:
                if child.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], timeout=15)
                    else:
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
                if os.name != 'nt':
                    # This session was created solely for this case, including descendants.
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        assert code == 0, (intent, (report / 'case.log').read_text(encoding='utf-8')[-5000:])
        record = json.loads((report / 'browser-result.json').read_text(encoding='utf-8'))
        assert record['result'] == 'PASS' and record['no_execution_or_credit']
        rows.append({'intent': intent, 'result': 'PASS'})
        (out / 'result.json').write_text(json.dumps({'result': 'PASS' if len(rows) == 3 else 'RUNNING', 'source_sha': source_sha, 'rows': rows}, indent=2), encoding='utf-8')
    assert len(rows) == 3
    print('All three native browser journeys PASS')

if __name__ == '__main__':
    main()
