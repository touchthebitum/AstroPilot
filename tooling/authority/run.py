"""Sequential cross-OS logical snapshots; no live sync or merge implementation."""
from pathlib import Path,PurePosixPath
import os,sys,subprocess,json,hashlib,shutil,zipfile,platform
SOURCE=Path(os.environ['PRODUCT_SOURCE']).resolve();OUT=Path(os.environ['AUTHORITY_OUT']).resolve();STAGE=os.environ['AUTHORITY_STAGE'];TOOLS=Path(__file__).resolve().parent
SHA='9afb40bd1e36d67f7a9e11e55f8fa28e6880f64d'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==SHA
OUT.mkdir(parents=True,exist_ok=False);CASES=OUT/'cases';CASES.mkdir();SNAPS=OUT/'snapshots';SNAPS.mkdir();ROWS=[]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inv(root):return {p.relative_to(root).as_posix():{'size':p.stat().st_size,'sha256':digest(p)} for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'}
def newcase(name):
 c=CASES/name;c.mkdir();(c/'QUALIFICATION_ONLY').write_text('PUBLIC SYNTHETIC AUTHORITY ONLY',encoding='utf-8');return c
def env(c):
 e={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))};e.update(CASE_ROOT=str(c),PRODUCT_SOURCE=str(SOURCE),PYTHONUTF8='1')
 for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','ASTROPILOT_DATA_DIR'):
  p=c/key;p.mkdir(exist_ok=True);e[key]=str(p)
 return e
def worker(c,mode):
 e=env(c);e['AUTHORITY_MODE']=mode
 with (c/(mode+'.log')).open('w',encoding='utf-8') as log:r=subprocess.run([sys.executable,str(TOOLS/'worker.py')],cwd=SOURCE,env=e,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 assert r.returncode==0,(c.name,mode,(c/(mode+'.log')).read_text(encoding='utf-8')[-6000:])
 if (c/'result.json').exists():ROWS.append({'case':c.name,**json.loads((c/'result.json').read_text(encoding='utf-8'))})
def freeze(c,name):
 d=SNAPS/name;d.mkdir();shutil.copy2(c/'context.json',d/'context.json');data=d/'data';data.mkdir()
 allowed={'decision_lineage','decision_acceptance_lineage','execution_lineage','decision_forecast_evidence','field_observations','outcome_evaluations'}
 for p in (c/'data').rglob('*.json'):
  rel=p.relative_to(c/'data')
  assert (len(rel.parts)==1 and rel.name in ('user_profile.json','user_filters.json')) or rel.parts[0] in allowed,rel
  dest=data/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
 profile=json.loads((data/'user_profile.json').read_text(encoding='utf-8'));context=json.loads((d/'context.json').read_text(encoding='utf-8'))
 manifest={'source_sha':SHA,'source_os':platform.platform(),'files':inv(d),'revision':profile['profile_revision'],'profile_sha256':digest(data/'user_profile.json'),'totals':context['totals'],'cursor_key_transferred':False,'guardian_attestation_transferred':False}
 (d/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');return d

def validate(d):
 m=json.loads((d/'manifest.json').read_text(encoding='utf-8'));assert m['source_sha']==SHA and inv(d)==m['files'],'Snapshot inventory mismatch'
 assert not any(p.suffix in ('.key','.lock') or 'guardian' in p.name.lower() for p in d.rglob('*'))
 return m

def restore(d,name):
 validate(d) # Verify BEFORE creating or activating the destination.
 c=newcase(name);shutil.copytree(d/'data',c/'data');shutil.copy2(d/'context.json',c/'context.json');assert not (c/'data/.outcome_history_cursor.key').exists();return c

def receive():
 archive=Path(os.environ['AUTHORITY_INPUT']);folder=OUT/'incoming';folder.mkdir()
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for i in z.infolist():
   p=PurePosixPath(i.filename);assert not p.is_absolute() and '..' not in p.parts and not (i.external_attr>>16)&0o170000==0o120000
  z.extractall(folder)
 for d in folder.iterdir():validate(d)
 return folder

def faults(a,b):
 # An external trusted manifest refuses a mixed same-revision profile before activation.
 bad=OUT/'manifest-negative';shutil.copytree(a,bad);shutil.copy2(b/'data/user_profile.json',bad/'data/user_profile.json')
 try:validate(bad)
 except AssertionError:ROWS.append({'case':'external_manifest_mixed_equal_revision','result':'PASS','activation_refused':True})
 else:raise AssertionError('External manifest accepted a divergent profile')
 # Separately inject inconsistent graphs after activation to test the real runtime refusal.
 for name,good,other in [('profile_b_stores_a',a,b),('profile_a_stores_b',b,a)]:
  c=restore(good,name);shutil.copy2(other/'data/user_profile.json',c/'data/user_profile.json');worker(c,'reject_mixed')
 c=restore(a,'missing_branch_execution');(c/'data/execution_lineage/authority-execution-fork_a.json').unlink();worker(c,'reject_mixed')
 # Explicit return to a coherent authority, never reconstruct or combine ledgers.
 c=restore(a,'recovered_selected_a');worker(c,'verify');validate(a);validate(b)

def export(names):
 archive=OUT/'transfer.zip'
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for name in names:
   d=SNAPS/name;validate(d)
   for p in d.rglob('*'):
    if p.is_file():z.write(p,p.relative_to(SNAPS).as_posix())
 return digest(archive)

if STAGE=='mac_seed':
 c=newcase('base')
 with (c/'seed.log').open('w',encoding='utf-8') as log:subprocess.run([sys.executable,str(TOOLS/'seed.py')],env=env(c),cwd=SOURCE,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
 worker(c,'init');worker(c,'verify');base=freeze(c,'base')
 a=restore(base,'fork_a');worker(a,'fork_a');worker(a,'verify');freeze(a,'a');transport=export(['base','a'])
elif STAGE=='windows':
 incoming=receive();base=incoming/'base';a=incoming/'a'
 c=restore(base,'base_from_mac');worker(c,'verify')
 c=restore(a,'a_from_mac');worker(c,'verify')
 c=restore(base,'fork_b');worker(c,'fork_b');worker(c,'verify');b=freeze(c,'b')
 ma=validate(a);mb=validate(b);assert ma['revision']==mb['revision'] and ma['profile_sha256']!=mb['profile_sha256'];assert ma['totals']!=mb['totals']
 ROWS.append({'case':'divergent_equal_revision','result':'PASS','revision':ma['revision'],'a':ma['totals'],'b':mb['totals'],'automatic_merge':'not implemented or claimed'})
 faults(a,b);shutil.copytree(a,SNAPS/'a');transport=export(['a','b'])
elif STAGE=='mac_return':
 incoming=receive();a=incoming/'a';b=incoming/'b';c=restore(b,'b_from_windows');worker(c,'verify');faults(a,b)
 for name in ('a','b'):shutil.copytree(incoming/name,SNAPS/name)
 transport=export(['a','b'])
else:raise AssertionError(STAGE)
for d in SNAPS.iterdir():validate(d)
proof={'result':'PASS','stage':STAGE,'source_sha':SHA,'platform':platform.platform(),'rows':ROWS,'transfer_sha256':transport,'real_profile_used':False,'public_api_created_credits':True,'manifest_is_external_lab_precondition':True,'signature_or_submission':False,'product_backup_or_sync_api_added':False}
(OUT/'result.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print('PASS',STAGE,len(ROWS),'checks')
