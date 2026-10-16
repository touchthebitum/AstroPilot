"""Compare actual downloaded artifacts, hashes, API retention and job outcomes."""
from pathlib import Path
import os,json,hashlib,datetime,xml.etree.ElementTree as ET
root=Path('downloaded');jobs=json.loads(Path('jobs.json').read_text())['jobs'];artifacts=json.loads(Path('artifacts.json').read_text())['artifacts'];sha=os.environ['CANDIDATE_SHA'];expected_names=set();rows=[]
for label in ('windows-2022','macos-latest'):
 for mode in ('success','failure'):
  name='probe ('+label+', '+mode+')';job=next(j for j in jobs if j['name']==name);expected='success' if mode=='success' else 'failure';assert job['conclusion']==expected,(name,job['conclusion'])
  test=next(s for s in job['steps'] if s['name']=='Run public test');assert test['conclusion']==expected
  for step in ('Export JUnit even after failure','Export browser directory even after failure','Export public manifest even after failure'):assert next(s for s in job['steps'] if s['name']==step)['conclusion']=='success'
  candidate=next(s for s in job['steps'] if s['name']=='Export candidate-shaped fixture only after success');assert candidate['conclusion']==('success' if mode=='success' else 'skipped')
  metadata='metadata-'+label+'-'+mode;expected_names.add(metadata);m=json.loads((root/metadata/'manifest.json').read_text(encoding='utf-8'));assert m['source_sha']==sha and m['expected_test_success']==(mode=='success')
  for artifact,entry in m['expected_artifacts'].items():
   expected_names.add(artifact);folder=root/artifact;actual={p.relative_to(folder).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in folder.rglob('*') if p.is_file()};assert actual==entry['files'],(artifact,actual,entry['files'])
   record=next(a for a in artifacts if a['name']==artifact);start=datetime.datetime.fromisoformat(record['created_at'].replace('Z','+00:00'));end=datetime.datetime.fromisoformat(record['expires_at'].replace('Z','+00:00'));days=(end-start).total_seconds()/86400;assert abs(days-entry['days'])<.02,(artifact,days)
  xml=root/('profile-recovery-'+label+'-'+mode)/'profile-recovery.xml';suite=ET.parse(xml).getroot();assert suite.attrib['tests']=='1' and int(suite.attrib['failures'])==(mode=='failure')
  rows.append({'os':label,'mode':mode,'test_job_conclusion':job['conclusion'],'exported_files_match':True,'retention_days_match':True,'junit_failures':int(suite.attrib['failures'])})
assert set(p.name for p in root.iterdir())==expected_names
assert set(a['name'] for a in artifacts)==expected_names
assert not any(p.name in ('user_profile.json','cursor.key','.env','secret.txt') for p in root.rglob('*') if p.is_file())
Path('verification.json').write_text(json.dumps({'result':'PASS','source_sha':sha,'rows':rows,'artifact_count':len(expected_names),'intentional_failure_jobs_remain_failed':True,'sensitive_and_hidden_sentinels_absent':True,'data_real_or_signing_used':False},indent=2),encoding='utf-8')
print('PASS: exact bytes, scopes, names, retention and original failure outcomes')
