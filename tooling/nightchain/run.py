from pathlib import Path
import os,sys,json,subprocess
ROOT=Path(os.environ['PRODUCT_SOURCE']).resolve();OUT=Path(os.environ['NIGHT_CHAIN_PROOF']).resolve();OUT.mkdir(parents=True,exist_ok=False)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()=='dad6e438b8ba0f5ce52d59457ce503e030911d80'
rows=[]
scenarios=('fixed_ha','fixed_oiii','cross_midnight','duration','daytime','cloudy','unavailable','optical_missing','config_changed','dst_ambiguous','dst_nonexistent')
for name in os.environ.get('NIGHT_SCENARIOS',','.join(scenarios)).split(','):
 case=OUT/name;case.mkdir();(case/'QUALIFICATION_ONLY').write_text('PUBLIC FIXTURE ONLY')
 env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))};env.update(CASE_ROOT=str(case),SCENARIO=name,WEATHER_MODE=name if name in ('cloudy','unavailable') else 'clear')
 if name=='dst_ambiguous':env['QUALIFICATION_CLOCK']='2026-10-24T12:00:00+00:00'
 if name=='dst_nonexistent':env['QUALIFICATION_CLOCK']='2026-03-28T12:00:00+00:00'
 with (case/'worker.log').open('wb') as f:r=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('worker.py'))],cwd=ROOT,env=env,stdout=f,stderr=f,timeout=300)
 assert r.returncode==0,(name,(case/'worker.log').read_text()[-3500:])
 rows.append(json.loads((case/'result.json').read_text()))
 (OUT/'qualification.json').write_text(json.dumps({'result':'RUNNING','rows':rows},indent=2)+'\n')
print('API cases PASS:',len(rows))
(OUT/'qualification.json').write_text(json.dumps({'result':'PASS','product_sha':'dad6e438b8ba0f5ce52d59457ce503e030911d80','rows':rows},indent=2)+'\n')
