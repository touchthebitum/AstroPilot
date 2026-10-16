from fixture import *
from datetime import timedelta
from zoneinfo import ZoneInfo
seed()
zone=os.environ['SITE_ZONE']
start=(REFERENCE.astimezone(ZoneInfo(zone)).date()+timedelta(days=1)).isoformat()+'T00:30'
end=start[:10]+'T03:30'
availability={'mode':'fixed_window','start_local':start,'end_local':end}
with TestClient(app()) as c:
 r=c.post('/v1/tonight',json={'availability':availability});assert r.status_code==200,r.text
 b=r.json();assert set(b['viable_acquisition_intent_ids'])=={'sh2-129_ha','ou4_oiii'},b
 assert b['night_date']==(REFERENCE.astimezone(ZoneInfo(zone)).date()).isoformat(),b
 (CASE/'fixture.json').write_text(json.dumps({'response':b,'availability':availability,'reference':REFERENCE.isoformat(),'zone':zone},indent=2),encoding='utf-8')
 assert not list((CASE/'data').rglob('*mission*.json')),'No mission should have been seeded'
 print('Public pending decision prepared',zone,b['night_date'])
