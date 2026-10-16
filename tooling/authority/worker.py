"""Actual production API on one isolated public copy per process."""
import os,sys,json,hashlib
from pathlib import Path
SOURCE=Path(os.environ['PRODUCT_SOURCE']);CASE=Path(os.environ['CASE_ROOT']);MODE=os.environ['AUTHORITY_MODE']
sys.path.insert(0,str(SOURCE/'scripts/ci/night_chain'))
from common import *

def inventory():
 return {p.relative_to(CASE/'data').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((CASE/'data').rglob('*.json')) if p.is_file()}
def request(c,method,path,body=None,status=200):
 r=c.request(method,path,json=body) if body is not None else c.request(method,path)
 assert r.status_code==status,(method,path,r.status_code,r.text)
 return r.json()
def revision():return json.loads((CASE/'data/user_profile.json').read_text(encoding='utf-8'))['profile_revision']
def credit(c,entry,expected=None):
 return request(c,'POST','/v1/executions/'+entry['execution_id']+'/intent-progress-credit',{'expected_revision':revision() if expected is None else expected,'evidence_ids':[entry['evidence_id']],'confirm_historical_baseline':entry['label']=='ha'})
def add(c,context,label,suffix,seconds):
 eid='authority-execution-'+suffix;mid=context['missions'][label]['mission_id'];entry={'label':label,'execution_id':eid,'evidence_id':'authority-evidence-'+suffix}
 request(c,'POST','/v1/executions',{'execution_id':eid,'mission_id':mid})
 b={'execution_id':eid,'mission_id':mid,'status':'in_progress','actual_start':'2026-10-15T22:30:00+00:00','actual_end':None,'actual_duration':None}
 request(c,'POST','/v1/execution-transitions',b);b.update(status='completed',actual_end='2026-10-15T23:30:00+00:00',actual_duration=3600);request(c,'POST','/v1/execution-transitions',b)
 request(c,'POST','/v1/outcome-evidence',{'evidence_id':entry['evidence_id'],'execution_id':eid,'category':'acquisition','observed_at':'2026-10-15T23:30:00+00:00','source':'user','usable_integration_duration':seconds})
 assert credit(c,entry)['status']=='applied'
 session=request(c,'GET','/v1/executions/'+eid+'/session');entry['acquired_after_seconds']=session['acquired_after_seconds'];context['credits'].append(entry)

def check(c,context):
 p=request(c,'GET','/v1/projects/Sh2-129/progress');totals={i['acquisition_intent_id']:i['effective_total_seconds'] for i in p['intent_progress_breakdown']};assert totals==context['totals'],(totals,context['totals'])
 for entry in context['credits']:
  s=request(c,'GET','/v1/executions/'+entry['execution_id']+'/session');assert s['acquired_after_seconds']==entry['acquired_after_seconds']
  for _ in range(3):assert credit(c,entry)['status']=='already_applied'
 return totals

context_path=CASE/'context.json'
if MODE=='init':
 context={'missions':json.loads((CASE/'missions.json').read_text(encoding='utf-8')),'credits':[],'totals':{'sh2-129_ha':5400,'ou4_oiii':900}}
 with TestClient(app()) as c:
  add(c,context,'ha','common-ha',1800);add(c,context,'oiii','common-oiii',900);check(c,context)
 context_path.write_text(json.dumps(context,indent=2),encoding='utf-8')
elif MODE in ('fork_a','fork_b'):
 context=json.loads(context_path.read_text(encoding='utf-8'));label='ha' if MODE=='fork_a' else 'oiii'
 with TestClient(app()) as c:add(c,context,label,MODE,600)
 context['totals']['sh2-129_ha' if label=='ha' else 'ou4_oiii']+=600;context_path.write_text(json.dumps(context,indent=2),encoding='utf-8')
elif MODE=='verify':
 context=json.loads(context_path.read_text(encoding='utf-8'));before=inventory();rev=revision();rows=[]
 for boot in range(2):
  with TestClient(app()) as c:
   totals=check(c,context)
   # Stale CAS is meaningful within this authority, not a cross-fork ordering rule.
   r=c.put('/v1/projects/Sh2-129/progress',json={'expected_revision':rev-1,'acquisition_intent_targets':[{'acquisition_intent_id':'sh2-129_ha','target_hours':7}]});assert r.status_code==409,r.text
   rows.append({'boot':boot+1,'totals':totals,'replays':len(context['credits'])*3,'stale_revision_http':r.status_code})
  assert inventory()==before,'Read/replay/stale edit changed authority'
 key=CASE/'data/.outcome_history_cursor.key';assert key.is_file()
 (CASE/'result.json').write_text(json.dumps({'result':'PASS','mode':MODE,'rows':rows,'revision':rev,'profile_sha256':before['user_profile.json'],'authority_sha256':before,'local_cursor_key_sha256':hashlib.sha256(key.read_bytes()).hexdigest(),'canonical_bytes_unchanged':True},indent=2),encoding='utf-8')
elif MODE=='reject_mixed':
 before=inventory();rev=revision();rows=[]
 for boot in range(2):
  with TestClient(app()) as c:
   read=request(c,'GET','/v1/projects/Sh2-129/progress',status=503);assert read['detail']['code']=='project_credit_inconsistent'
   edited=request(c,'PUT','/v1/projects/Sh2-129/progress',{'expected_revision':rev,'acquisition_intent_targets':[{'acquisition_intent_id':'sh2-129_ha','target_hours':7}]},status=503);assert edited['detail']['code']=='project_credit_inconsistent'
   rows.append({'boot':boot+1,'read':read,'edit':edited})
  assert inventory()==before,'Rejected mixed snapshot changed authority'
 (CASE/'result.json').write_text(json.dumps({'result':'PASS','mode':MODE,'rows':rows,'canonical_bytes_unchanged':True},indent=2),encoding='utf-8')
else:raise AssertionError(MODE)
print(MODE,'PASS')
