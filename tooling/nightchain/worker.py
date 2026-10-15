from common import *
import platform
name=os.environ['SCENARIO'];equipment='fra400_2600' if name=='optical_missing' else 'samyang_183'
seed(equipment);before=profile_hash();record={'scenario':name,'product_sha':SHA,'reference_utc':REF.isoformat(),'os':platform.platform(),'weather':MODE,'equipment':equipment,'thresholds_modified':False}
av={'mode':'fixed_window','start_local':'2026-10-16T00:30','end_local':'2026-10-16T03:30'}
if name=='cross_midnight':av={'mode':'fixed_window','start_local':'2026-10-15T23:30','end_local':'2026-10-15T02:30'}
if name=='duration':av={'mode':'duration','duration':'PT1H'}
if name=='daytime':av={'mode':'fixed_window','start_local':'2026-10-15T10:00','end_local':'2026-10-15T12:00'}
if name=='dst_ambiguous':av={'mode':'fixed_window','start_local':'2026-10-25T02:30','end_local':'2026-10-25T04:30'}
if name=='dst_nonexistent':av={'mode':'fixed_window','start_local':'2026-03-29T02:30','end_local':'2026-03-29T04:30'}
record['availability']=av
with TestClient(app()) as c:
 r=c.post('/v1/tonight',json={'availability':av});body=r.json();record['preparation']={'http':r.status_code,'body':body}
 (CASE/'result.json').write_text(json.dumps(record,indent=2))
 if name.startswith('dst_'):
  assert r.status_code==422,body
  expected='session_availability_local_time_'+('ambiguous' if name=='dst_ambiguous' else 'nonexistent');assert body['detail']['code']==expected,body
 elif MODE=='unavailable':assert r.status_code==503 and body['detail']['code']=='weather_unavailable',body
 elif MODE=='cloudy' or name in ('daytime','optical_missing'):
  assert r.status_code==200 and body['status'] in ('no_mission','no_night'),body
  assert not body.get('acquisition_intent_choice_available'),body
 else:
  assert r.status_code==200,body
  if name=='duration' and not body.get('acquisition_intent_choice_available') and body['status']=='no_mission':
   record['duration_refusal_observed']=body.get('creation_refusal')
  else:
   assert body['catalog_key']=='Sh2-129' and set(body['viable_acquisition_intent_ids'])=={'sh2-129_ha','ou4_oiii'},body
   if name!='duration':assert body['night_date']=='2026-10-15',body
   if name=='config_changed':
    config=c.get('/v1/configuration').json()
    v=c.put('/v1/configuration',json={'expected_revision':config['profile_revision'],'site':{'name':'PUBLIC CHANGED SITE','latitude':46.888,'longitude':6.55,'bortle':5},'equipment':{'preset_id':'samyang_183'},'projects':{'Sh2-129':{'hours':0,'target_hours':20,'importance':9}}});assert v.status_code==200,v.json();before=profile_hash()
   intent='ou4_oiii' if name=='fixed_oiii' else 'sh2-129_ha'
   q=selection(body,intent,'public-'+name)
   accepted=c.post('/v1/decision-selections',json=q);record['confirmation']={'http':accepted.status_code,'body':accepted.json()}
   if name=='config_changed':
    # Canonical acceptance remains a historical snapshot by documented contract.
    assert accepted.status_code==200 and accepted.json()['status']=='accepted',accepted.json()
    record['historical_acceptance_preserved']=True
    assert c.get('/v1/accepted-mission/current').json() is None
   else:
    assert accepted.status_code==200 and accepted.json()['status']=='accepted',accepted.json()
    mission=accepted.json()['mission'];record['mission']=mission
    assert accepted.json()['selected_acquisition_intent_id']==intent
    start=datetime.fromisoformat(mission['window_start']);end=datetime.fromisoformat(mission['window_end']);assert end>start
    if name!='duration':
     lower=datetime(2026,10,15,21,30,tzinfo=timezone.utc) if name=='cross_midnight' else datetime(2026,10,15,22,30,tzinfo=timezone.utc)
     upper=datetime(2026,10,16,0,30,tzinfo=timezone.utc) if name=='cross_midnight' else datetime(2026,10,16,1,30,tzinfo=timezone.utc)
     assert start>=lower and end<=upper,(start,end)
    else:assert (end-start).total_seconds()<=3600
    replay=c.post('/v1/decision-selections',json=q);assert replay.status_code==200 and replay.json()['mission_id']==accepted.json()['mission_id'],replay.json();record['idempotent_confirmation']=True
    record['accepted_id']=accepted.json()['mission_id']
 # Preparation can persist decision/evidence; it must never start an execution or credit.
 assert c.get('/v1/execution-sessions').json()==[],c.get('/v1/execution-sessions').json()
 current=c.get('/v1/accepted-mission/current');record['current_before_restart']=current.json()
 assert profile_hash()==before,'Selection changed progress profile'
with TestClient(app()) as c:
 current=c.get('/v1/accepted-mission/current');record['current_after_restart']=current.json()
 assert current.status_code==200,current.json()
 if record.get('accepted_id'):assert current.json()['mission_id']==record['accepted_id'],current.json()
 else:assert current.json() is None,current.json()
 assert profile_hash()==before
record.update(result='PASS',profile_unchanged=True,legacy_inventory_absent=not (CASE/'data/user_filters.json').exists(),new_execution_or_credit=False)
(CASE/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'scenario':name,'result':'PASS','night_date':body.get('night_date'),'confirmation_http':record.get('confirmation',{}).get('http')}))
