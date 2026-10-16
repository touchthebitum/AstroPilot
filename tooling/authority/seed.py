"""Generate public canonical decisions/acceptances with production APIs, not invented stores."""
import os,sys,json
from pathlib import Path
source=Path(os.environ['PRODUCT_SOURCE'])
sys.path.insert(0,str(source/'scripts/ci/night_chain'))
from common import *
seed()
records={}
with TestClient(app()) as c:
 config=c.get('/v1/configuration').json()
 r=c.put('/v1/projects/Sh2-129/progress',json={'expected_revision':config['profile_revision'],'imaging_field_id':'sh2-129_ou4','acquisition_intent_progress':[{'acquisition_intent_id':i,'acquired_duration_manual':3600 if i=='sh2-129_ha' else 0} for i in ('sh2-129_ha','ou4_oiii')],'acquisition_intent_targets':[{'acquisition_intent_id':i,'target_hours':6} for i in ('sh2-129_ha','ou4_oiii')]})
 assert r.status_code==200,r.text
 for label,intent in [('ha','sh2-129_ha'),('oiii','ou4_oiii')]:
  r=c.post('/v1/tonight',json={'availability':{'mode':'fixed_window','start_local':'2026-10-16T00:30','end_local':'2026-10-16T03:30'}});assert r.status_code==200,r.text
  b=r.json();assert b['night_date']=='2026-10-15',b
  q={'acceptance_request_id':'public-recovery-'+label,'decision_id':b['decision_id'],'source':'primary_recommendation','selected_catalog_key':b['catalog_key'],'acquisition_intent_id':intent,'selected_at':REFERENCE.isoformat()}
  r=c.post('/v1/decision-selections',json=q);assert r.status_code==200,r.text
  records[label]=r.json();assert records[label]['status']=='accepted'
(CASE/'missions.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
