"""Build a frozen probe and compare it to source with identical Chrome/flags."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

tools = Path(__file__).resolve().parent
source = Path('candidate').resolve()
root = Path(os.environ['RUNNER_TEMP']) / 'network-matrix'
root.mkdir()
sys.path.insert(0, str(source / 'scripts/ci/night_chain'))
from setup_browser import install
chrome, provenance = install()
kit = root / 'kit'
kit.mkdir()
(kit/'kit.json').write_text('{"browser":"browser/chrome.exe"}')
shutil.copytree(chrome.parent, kit / 'browser')
venv = root / 'venv'
subprocess.run(['uv', 'venv', '--python', '3.13.5', str(venv)], check=True)
python = venv / 'Scripts/python.exe'
subprocess.run(['uv', 'pip', 'sync', '--require-hashes', '--python', str(python), str(tools / 'requirements.txt')], check=True)
subprocess.run([str(python), '-m', 'PyInstaller', '--noconfirm','--clean','--onedir','--console','--name','NetworkProbe','--collect-data','tzdata',
                '--distpath',str(root/'dist'),'--workpath',str(root/'build'),'--specpath',str(root/'spec'),str(tools/'network_probe.py')],check=True,cwd=tools)
rows = []
for name, frozen, helper, cwdkit, longpath in [
    ('source-helper',False,True,False,False),
    ('frozen-helper',True,True,False,False),
    ('frozen-cwd-kit',True,True,True,False),
    ('frozen-long-profile',True,True,False,True),
    ('frozen-cwd-kit-long',True,True,True,True),
    ('frozen-direct-cwd-kit-long',True,False,True,True),
]:
    env = {k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
    env['PYTHONUTF8'] = '1'
    for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME'):
        folder = root / 'environment' / name / key
        folder.mkdir(parents=True)
        env[key] = str(folder)
    case = root/name
    if longpath:
        parent = root / ('long-profile-'+'x'*65)
        parent.mkdir(exist_ok=True)
        case = parent/name
    command = [str(root/'dist/NetworkProbe/NetworkProbe.exe')] if frozen else [str(python),str(tools/'network_probe.py')]
    command += [str(kit),str(case),str(tools/'network_health.cjs'),'--verbose','--forecast']
    if helper:
        command += ['--actual-helper']
    p = subprocess.run(command, env=env, cwd=kit if cwdkit else tools, capture_output=True, text=True, timeout=100)
    (root/(name+'.stdout.log')).write_text(p.stdout)
    (root/(name+'.stderr.log')).write_text(p.stderr)
    result = case/'result.json'
    rows.append({'name':name,'exit':p.returncode,'result':json.loads(result.read_text()) if result.exists() else None})
    # Export diagnostics without the browser profile or TLS key.
    if longpath:
        out=root/name;out.mkdir()
        for filename in ('result.json','browser.log'):
            if (case/filename).exists(): shutil.copy2(case/filename,out/filename)
(root/'matrix.json').write_text(json.dumps({'provenance':provenance,'cases':rows},indent=2))
print(json.dumps({'cases':[{**r,'result':{k:v for k,v in (r['result'] or {}).items() if k not in ('environment','command','launcher_dll_directory')}} for r in rows]},indent=2))
assert all(r['exit']==0 and r['result']['health_exit']==0 for r in rows)
