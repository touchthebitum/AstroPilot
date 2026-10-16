"""Preserve JS assertions while avoiding Windows' CreateProcess command limit."""
import hashlib
import json
import os
from pathlib import Path
import subprocess


def pytest_configure(config):
    if os.name != 'nt':
        return
    original = subprocess.run
    def portable(args, *pos, **kw):
        if not (isinstance(args, list) and len(args) == 3 and args[1] == '-e'
                and Path(args[0]).stem.lower() in ('node', 'node.exe')
                and len(subprocess.list2cmdline(args)) >= 32767):
            return original(args, *pos, **kw)
        assert 'input' not in kw and 'stdin' not in kw
        code = args[2]
        record = {'command_chars': len(subprocess.list2cmdline(args)), 'script_chars': len(code),
                  'script_sha256': hashlib.sha256(code.encode('utf-8')).hexdigest(),
                  'transport': 'stdin', 'assertions_changed': False}
        kw.update(input=code, timeout=kw.get('timeout') or 30)
        try:
            returned = original([args[0], '-'], *pos, **kw)
            record['exit'] = returned.returncode
            return returned
        finally:
            with Path(os.environ['NODE_STDIN_PROOF']).open('a', encoding='utf-8') as log:
                log.write(json.dumps(record)+'\n')
    subprocess.run = portable
