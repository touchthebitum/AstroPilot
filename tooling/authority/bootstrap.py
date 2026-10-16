from pathlib import Path
import os,subprocess
source=Path('candidate').resolve();tools=Path('operations/tooling/authority').resolve();root=Path(os.environ['RUNNER_TEMP'])/'authority-tools';root.mkdir()
env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','UV_CACHE_DIR'):
 p=root/key;p.mkdir();env[key]=str(p)
env.update(PYTHONUTF8='1',UV_NO_ENV_FILE='1',UV_PROJECT_ENVIRONMENT=str(root/'venv'),PRODUCT_SOURCE=str(source),AUTHORITY_OUT=str(Path(os.environ['RUNNER_TEMP'])/'authority-proof'))
with (root/'dependencies.log').open('w',encoding='utf-8') as log:subprocess.run(['uv','sync','--locked','--extra','test'],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
python=root/('venv/Scripts/python.exe' if os.name=='nt' else 'venv/bin/python')
subprocess.run([str(python),str(tools/'run.py')],env=env,cwd=source,check=True,timeout=600)
