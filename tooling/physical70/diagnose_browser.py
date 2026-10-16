"""Native Windows reproduction; disposable browser and profiles only."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

sys.path.insert(0, str(Path('candidate/scripts/ci/night_chain').resolve()))
from setup_browser import install
from browser_permissions import configure_browser

root = Path(os.environ['RUNNER_TEMP']) / 'sandbox-proof'
root.mkdir()
exe, provenance = install()
browser = exe.parent
browser.rename(browser.parent / 'browser')
browser = browser.parent / 'browser'
exe = browser / 'chrome.exe'
who = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True).strip().split(',')[-1].strip('"')
def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90)
def acl(path):
    return subprocess.check_output(['pwsh', '-NoProfile', '-Command', '(Get-Acl -LiteralPath $env:NIGHTMERIT_ACL_PROBE).Sddl'], env={**os.environ, 'NIGHTMERIT_ACL_PROBE': str(path)}, text=True).strip()
# Replace inherited access on this newly downloaded, disposable browser only.
run(['icacls', str(browser), '/inheritance:r'])
run(['icacls', str(browser), '/grant:r', '*' + who + ':(OI)(CI)(F)', '*S-1-5-18:(OI)(CI)(F)'])
before_parent = acl(browser.parent)
before = acl(browser)
hashes = {str(p.relative_to(browser)): hashlib.sha256(p.read_bytes()).hexdigest() for p in browser.rglob('*') if p.is_file()}
(root / 'index.html').write_text('<h1>NIGHTMERIT_SANDBOX_OK</h1>')
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:' + str(server.server_port)
def launch(name):
    args = [str(exe), '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--user-data-dir=' + str(root / ('profile-' + name)), '--dump-dom', url]
    with (root / (name + '.stderr.log')).open('wb') as log:
        child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log)
        try:
            stdout, _ = child.communicate(timeout=45)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, timeout=15)
            stdout, _ = child.communicate(timeout=10)
    (root / (name + '.html')).write_bytes(stdout)
    text = (root / (name + '.stderr.log')).read_text(errors='replace')
    return {'exit': child.returncode, 'page_ok': b'NIGHTMERIT_SANDBOX_OK' in stdout, 'access_error': 'Sandbox cannot access executable' in text, 'network_restart': 'Network service crashed or was terminated' in text, 'command': args}
result = {'provenance': provenance, 'before_acl': before, 'baseline': launch('before')}
result.update(configuration=configure_browser(browser.parent), after_acl=acl(browser), corrected=launch('after'))
result['parent_acl_unchanged'] = before_parent == acl(browser.parent)
result['browser_bytes_unchanged'] = hashes == {str(p.relative_to(browser)): hashlib.sha256(p.read_bytes()).hexdigest() for p in browser.rglob('*') if p.is_file()}
(root / 'result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
server.shutdown()
assert result['baseline']['access_error'], 'Expected native reproduction was not observed'
assert result['corrected']['page_ok'] and not result['corrected']['access_error'] and not result['corrected']['network_restart']
assert result['parent_acl_unchanged'] and result['browser_bytes_unchanged']
