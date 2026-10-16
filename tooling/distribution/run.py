"""Isolated native contracts, without calling any actual signing/submission tool."""
from pathlib import Path
import os,sys,subprocess,json,shutil,xml.etree.ElementTree as ET,hashlib,zipfile
source=Path('candidate').resolve();baseline=Path('baseline').resolve();tools=Path(__file__).resolve().parent
out=Path(os.environ['RUNNER_TEMP'])/'distribution-proof';out.mkdir()
env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','ASTROPILOT_DATA_DIR','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','UV_CACHE_DIR'):
 p=out/'environment'/key;p.mkdir(parents=True);env[key]=str(p)
env.update(PYTHONUTF8='1',UV_NO_ENV_FILE='1',UV_PROJECT_ENVIRONMENT=str(out/'venv'),PRODUCT_SOURCE=str(source))
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip();assert sha==os.environ['CANDIDATE_SHA']
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=baseline,text=True).strip()=='a5c77a79087e3e50285ec4413b8b643f1f024747'
def run(args,cwd,name,expected=0):
 with (out/(name+'.log')).open('w',encoding='utf-8') as log:r=subprocess.run(args,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 assert r.returncode==expected,(name,r.returncode)
run(['uv','sync','--locked','--extra','test'],source,'dependencies')
python=out/('venv/Scripts/python.exe' if os.name=='nt' else 'venv/bin/python')
shutil.copy2(source/'tests/architecture/test_macos_release_source_identity.py',baseline/'tests/architecture/test_macos_release_source_identity.py')
run([str(python),'-m','pytest','-q','tests/architecture/test_macos_release_source_identity.py','-k','refuses_dirty_source_before_build','--junitxml',str(out/'baseline.xml')],baseline,'baseline',expected=1)
r=ET.parse(out/'baseline.xml');cases=r.findall('.//testcase');assert len(cases)==4 and all(c.find('failure') is not None for c in cases)
files=['test_macos_release_source_identity.py','test_packaging_contract.py','test_windows_packaging_contract.py','test_windows_installer_contract.py','test_windows_candidate_artifacts.py']
run([str(python),'-m','pytest','-q',*[str(source/'tests/architecture'/f) for f in files],str(tools/'test_release_gates.py'),'--junitxml',str(out/'candidate.xml')],source,'candidate')
r=ET.parse(out/'candidate.xml');cases=r.findall('.//testcase');new=[c for c in cases if 'macos_release_source_identity' in c.attrib.get('classname','')];assert len(new)==12 and all(c.find('skipped') is None and c.find('failure') is None and c.find('error') is None for c in new)
(out/'result.json').write_text(json.dumps({'result':'PASS','source_sha':sha,'baseline_sha':'a5c77a79087e3e50285ec4413b8b643f1f024747','baseline_expected_failures':4,'candidate_cases':len(cases),'candidate_skips':sum(c.find('skipped') is not None for c in cases),'new_regressions_passed':12,'gate_fault_cases':14,'signing_and_submission':'all simulated; no native signing command invoked','real_profile_used':False},indent=2),encoding='utf-8')
