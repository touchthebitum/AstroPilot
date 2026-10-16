"""Read-only reopen of an already qualified synthetic Windows profile."""
from pathlib import Path
import os,json,shutil,subprocess,sys
SOURCE=Path(os.environ['PRODUCT_SOURCE']).resolve();OUT=Path(os.environ['RECOVERY_PROOF']);SHA=os.environ['APPROVED_SHA'];EXE=Path(os.environ['CANDIDATE_EXE'])
import runtime
sys.path.insert(0,str(SOURCE/'scripts/ci/night_chain'))
from setup_browser import install
from qualify import browser,write
assert os.name=='nt'
OUT.mkdir(parents=True,exist_ok=False)
case=OUT/'winnipeg';case.mkdir();prior=Path(os.environ['RUNNER_TEMP'])/'prior-proof/proof/winnipeg'
shutil.copytree(prior/'data',case/'data');shutil.copy2(prior/'fixture.json',case/'fixture.json')
mission=json.loads((prior/'ui-accept-oiii/browser-result.json').read_text(encoding='utf-8'))
before=runtime.authority(case/'data');write(case/'authority-before-restart.json',before)
chrome,provenance=install();write(OUT/'browser-provenance.json',provenance)
with runtime.Server(EXE,case,SHA,'1.0.0b8'):
 result=browser(case,'oiii','reopen',chrome,mission)
 assert not any(t['request'] is not None for t in result['traffic']),result['traffic']
assert runtime.authority(case/'data')==before,'Read-only reshoot mutated canonical bytes'
write(OUT/'result.json',{'result':'PASS','source_sha':SHA,'read_only':True,'session_or_credit_created':False,'canonical_bytes_unchanged':True,'original_campaign':38921019839,'browser':result})
