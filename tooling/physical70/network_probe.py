"""Compare actual launcher functions in source and frozen form on disposable data."""
import ctypes
import functools
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

from controller import spawn, run_external
from browser_permissions import configure_browser
from forecast import Forecast


def main():
    kit, case, node_script = map(Path, sys.argv[1:4])
    verbose = '--verbose' in sys.argv
    forecast_enabled = '--forecast' in sys.argv
    case.mkdir()
    forecast = Forecast(case) if forecast_enabled else None
    if forecast:
        forecast.__enter__()
    (case / 'index.html').write_text('<h1>NIGHTMERIT_NETWORK_PROBE</h1>')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(case)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = case / 'browser-profile'
    profile.mkdir()
    url = 'http://127.0.0.1:' + str(server.server_port) + '/index.html'
    result = {'frozen': bool(getattr(sys, 'frozen', False)), 'forecast': forecast_enabled,
              'verbose': verbose, 'permissions': configure_browser(kit, run=run_external)}
    buf = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetDllDirectoryW(len(buf), buf)
    result['launcher_dll_directory'] = buf.value
    result['environment'] = {k: os.environ.get(k) for k in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','PATH','_PYI_APPLICATION_HOME_DIR')}
    args = [str(kit / 'browser/chrome.exe'), '--headless=new', '--disable-gpu', '--remote-debugging-port=0',
            '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
            '--user-data-dir=' + str(profile)]
    if verbose:
        args += ['--enable-logging=stderr', '--v=1']
    args += [url]
    logpath = case / 'browser.log'
    child = None
    try:
        with logpath.open('wb') as log:
            child = spawn(args, env=os.environ.copy(), stdout=log, stderr=log)
            endpoint = profile / 'DevToolsActivePort'
            end = time.monotonic() + 35
            while not endpoint.exists() and time.monotonic() < end:
                assert child.poll() is None, 'Browser exited before debugger startup'
                time.sleep(.1)
            port = endpoint.read_text().splitlines()[0]
            check = subprocess.run(['node', str(node_script), port, url], capture_output=True, text=True, timeout=35)
            result['health_exit'] = check.returncode
            result['health_stdout'] = check.stdout
            result['health_stderr'] = check.stderr
            time.sleep(5)
            text = logpath.read_text(errors='replace')
            result['access_error'] = 'Sandbox cannot access executable' in text
            result['network_restart'] = 'Network service crashed or was terminated' in text
            result['command'] = args
    finally:
        if child and child.poll() is None:
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=15)
            child.wait(timeout=10)
        server.shutdown()
        if forecast:
            forecast.__exit__()
        (case / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
