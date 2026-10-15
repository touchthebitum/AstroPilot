import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

base = Path.cwd().parent
baseline, candidate = base / 'baseline', base / 'candidate'
proof = Path(os.environ['RUNNER_TEMP']) / 'profile-recovery-proof'
proof.mkdir()
test = 'tests/api/test_profile_decoding_recovery.py'
shutil.copy2(candidate / test, baseline / test)
expected = {'baseline': 'dad6e438b8ba0f5ce52d59457ce503e030911d80',
            'candidate': os.environ['CANDIDATE_SHA']}
results = {}
for stage, source in [('baseline', baseline), ('candidate', candidate)]:
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    assert sha == expected[stage]
    env = os.environ.copy()
    root = proof / stage
    root.mkdir()
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'ASTROPILOT_DATA_DIR', 'TMP', 'TEMP', 'TMPDIR'):
        path = root / key
        path.mkdir()
        env[key] = str(path)
    env['PYTHONPATH'] = str(source)
    selected = [test]
    if stage == 'candidate':
        selected += ['tests/api/test_configuration_api.py', 'tests/api/test_durable_read_recovery.py',
                     'tests/api/test_intent_progress_persistence_diagnostics.py',
                     'tests/api/test_outcome_evaluation_api.py', 'tests/history',
                     'tests/guardian/test_guardian_scheduler_persistence.py',
                     'tests/guardian/test_guardian_renewal_api.py']
        selected += [str(p.relative_to(source)) for p in sorted((source / 'tests/architecture').glob('test_*persistence*.py'))]
    command = [sys.executable, '-m', 'pytest', *selected, '-q', '--tb=short', '--junitxml=' + str(root / 'tests.xml')]
    with (root / 'pytest.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
    suites = ET.parse(root / 'tests.xml').getroot()
    counts = {k: sum(int(s.get(k, 0)) for s in suites.iter('testsuite')) for k in ('tests', 'failures', 'errors', 'skipped')}
    results[stage] = {'sha': sha, 'exit_code': result.returncode, **counts}
    print(stage, results[stage], flush=True)
    (proof / 'result.json').write_text(json.dumps({'platform': sys.platform, 'python': sys.version, 'results': results}, indent=2))
    if stage == 'baseline':
        assert result.returncode == 1 and counts == {'tests': 11, 'failures': 9, 'errors': 0, 'skipped': 0}, (root / 'pytest.log').read_text()[-10000:]
    else:
        assert result.returncode == 0 and counts['failures'] == counts['errors'] == 0, (root / 'pytest.log').read_text()[-10000:]
