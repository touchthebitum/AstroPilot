"""Instrument generated public CJS only; never change source or force Node exit."""
import json
import os
from pathlib import Path
import subprocess
import time


def pytest_configure(config):
    original = subprocess.run
    out = Path(os.environ['NODE_DIAG_OUT'])
    out.mkdir(exist_ok=True)
    count = 0
    def observed(args, *a, **kw):
        nonlocal count
        if not isinstance(args, list) or len(args) != 2 or Path(str(args[1])).name != 'host-status-ui.cjs':
            return original(args, *a, **kw)
        count += 1
        script = Path(args[1])
        trace = out / (str(count) + '.jsonl')
        code = script.read_text(encoding='utf-8')
        assertion = "assert.deepEqual(calls,[['/v1/opportunity-alerts/status','GET']]);"
        assert code.count(assertion) == 1
        event = '''
const __fs = require('node:fs');
function __trace(event) {__fs.appendFileSync(TRACE_PATH,JSON.stringify({event,pid:process.pid,
 uptime:process.uptime(),monotonic_ns:process.hrtime.bigint().toString(),
 resources:process.getActiveResourcesInfo(),usage:process.resourceUsage()})+'\\n');}
__trace('script_enter');
process.on('beforeExit',()=>__trace('before_exit'));
process.on('exit',()=>__trace('exit'));
process.on('uncaughtExceptionMonitor',()=>__trace('uncaught_exception'));
'''.replace('TRACE_PATH', json.dumps(str(trace)))
        loaded = "\n(async()=>{"
        assert code.count(loaded) == 1
        code = code.replace(loaded, "\n__trace('ui_loaded');" + loaded)
        code = event + code.replace(assertion, assertion + "\n__trace('assertions_complete');")
        script.write_text(code, encoding='utf-8')
        start = time.monotonic()
        record = {'script': str(script), 'timeout_seconds': kw.get('timeout'), 'forced_exit': False}
        try:
            returned = original(args, *a, **kw)
            record.update(exit=returned.returncode)
            return returned
        except subprocess.TimeoutExpired as error:
            record.update(timeout=True, stdout=repr(error.stdout), stderr=repr(error.stderr))
            raise
        finally:
            record['parent_elapsed_seconds'] = time.monotonic() - start
            (out / (str(count) + '-parent.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
    subprocess.run = observed
