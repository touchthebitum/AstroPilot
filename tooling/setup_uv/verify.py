from pathlib import Path
import json
root=Path('downloaded');jobs=json.loads(Path('jobs.json').read_text())['jobs'];rows=[]
for os in ('windows-2022','macos-latest'):
 cachekeys=[]
 for mode in ('cold','warm','disabled','lock_failure','invalid_setup'):
  p=root/(mode+'-'+os)/'result.json';d=json.loads(p.read_text(encoding='utf-8'));assert d['source_sha']=='680090bfa3ceb56ba9394cb97f63942642139322'
  j=next(j for j in jobs if j['name']==mode+' ('+os+')');expected='failure' if mode in ('lock_failure','invalid_setup') else 'success';assert j['conclusion']==expected
  assert d['result'].startswith('PASS') and d['expected_job_conclusion']==expected
  if mode in ('cold','warm','lock_failure'):cachekeys.append(d['cache_key'])
  if mode in ('warm','lock_failure'):assert d['cache_hit']=='true' and d['restored_cache_canary']
  rows.append({'os':os,'mode':mode,'conclusion':j['conclusion'],'result':d['result'],'cache_hit':d.get('cache_hit')})
 assert len(set(cachekeys))==1 and cachekeys[0]
Path('verification.json').write_text(json.dumps({'result':'PASS','rows':rows,'negative_jobs_still_failed':True,'cache_key_consistent_per_os':True},indent=2),encoding='utf-8');print('PASS setup versions, locked tools, cold/restored/disabled cache and preserved failure outcomes')
