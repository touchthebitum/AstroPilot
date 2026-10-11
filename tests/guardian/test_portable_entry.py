import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('mode,module', [
    ('--guardian', 'astropilot.guardian_host'),
    ('--guardian-http-worker', 'astropilot.guardian_http_worker'),
])
def test_guardian_dispatch_does_not_import_web_launcher(mode, module):
    root = Path(__file__).resolve().parents[2]
    script = f'''
import importlib.abc, sys, types
class BlockWeb(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('astropilot.launcher', 'astropilot.app'):
            raise AssertionError('web initialized in Guardian mode')
sys.meta_path.insert(0, BlockWeb())
fake = types.ModuleType({module!r})
def main(args):
    assert args == ['sentinel']
    return 6
fake.main = main
sys.modules[{module!r}] = fake
sys.argv = ['AstroPilot', {mode!r}, 'sentinel']
from astropilot.portable_entry import main
assert main() == 6
'''
    subprocess.run([sys.executable, '-c', script], cwd=root, check=True, timeout=10)
