"""Qualification protocol only; not a product backup/restore feature.
A trusted inventory is frozen outside the payload and never replaced after damage.
Private profiles stay local. The normal production app is invoked without weather.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[2]
import session_seed as seed
STORES = {'decision_forecast_evidence','decision_lineage','execution_lineage',
          'field_observations','outcome_evaluations'}
LOCAL = {'.outcome_history_cursor.key','.outcome_history_cursor.key.lock',
         'guardian_runtime.json'}

class Rejected(ValueError): pass


def names_valid(names):
    seen=set()
    for name in names:
        p=PurePosixPath(name)
        if not name or p.is_absolute() or str(p)!=name or '..' in p.parts:
            raise Rejected('unsafe_relative_path')
        for part in p.parts:
            if '\\' in part or ':' in part or part.rstrip(' .')!=part:
                raise Rejected('nonportable_name')
            stem=part.split('.')[0].casefold()
            if stem in {'con','prn','aux','nul',*[f'com{i}' for i in range(1,10)],*[f'lpt{i}' for i in range(1,10)]}:
                raise Rejected('nonportable_name')
        folded=unicodedata.normalize('NFC',name).casefold()
        if folded in seen: raise Rejected('name_collision')
        seen.add(folded)


def inventory(root, strict_payload=False):
    result={}
    for p in sorted(root.rglob('*')):
        mode=p.lstat().st_mode
        if stat.S_ISLNK(mode): raise Rejected('symlink')
        if stat.S_ISDIR(mode): continue
        if not stat.S_ISREG(mode): raise Rejected('nonregular_file')
        name=p.relative_to(root).as_posix()
        excluded=(name in LOCAL or p.name.endswith('.lock') or name.startswith('Logs/'))
        if excluded:
            if strict_payload: raise Rejected('runtime_state_in_payload')
            continue
        if name!='user_profile.json' and not (p.relative_to(root).parts[0] in STORES and p.suffix=='.json'):
            raise Rejected('unclassified_file')
        payload=p.read_bytes()
        result[name]={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    names_valid(result)
    return result


def verify(root, manifest, strict=False):
    if inventory(root,strict)!=manifest: raise Rejected('snapshot_inventory_mismatch')


def clone_payload(source,destination,manifest):
    if destination.exists(): raise Rejected('destination_exists')
    verify(source,manifest)
    destination.mkdir(parents=True,exist_ok=False)
    for name in manifest:
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
    verify(destination,manifest,True)
    verify(source,manifest)


def archive_payload(source,archive,manifest):
    verify(source,manifest,True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in manifest: z.write(source/name,name)
    verify(source,manifest,True)


def restore_archive(archive,destination,manifest):
    if destination.exists(): raise Rejected('destination_exists')
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();names=[r.filename for r in infos]
        names_valid(names)
        if set(names)!=set(manifest): raise Rejected('archive_inventory_mismatch')
        for info in infos:
            if stat.S_ISLNK(info.external_attr>>16): raise Rejected('archive_symlink')
            if info.file_size!=manifest[info.filename]['bytes']: raise Rejected('archive_size_mismatch')
            with z.open(info) as f: payload=f.read(info.file_size+1)
            if hashlib.sha256(payload).hexdigest()!=manifest[info.filename]['sha256']:
                raise Rejected('archive_digest_mismatch')
        destination.mkdir(parents=True,exist_ok=False)
        for info in infos:
            target=destination/info.filename;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(z.read(info))
    verify(destination,manifest,True)


def qualify(destination,reference=None,existing_seed=None):
    out=Path(destination).resolve();out.mkdir(parents=True,exist_ok=False)
    source_case=out/'seed'
    if existing_seed:
        shutil.copytree(Path(existing_seed),source_case)
    else:
        with contextlib.redirect_stdout(io.StringIO()): seed.qualify(source_case,reference)
    source=source_case/'data'
    # Runtime attestation is explicitly excluded, never treated as portable live state.
    from datetime import datetime, timezone
    from astropilot.guardian_session_store import GuardianSessionStore
    from decision.models.guardian_live_session import GuardianLiveSessionEvidence
    from decision.models.guardian import GuardianSessionState
    GuardianSessionStore(source/'guardian_runtime.json').write(GuardianLiveSessionEvidence(
        GuardianSessionState.ACTIVE,datetime.now(timezone.utc),
        'caller_session_heartbeat_v1','CALLER_ASSERTED','qualification-execution-ha'))
    manifest=inventory(source)
    trusted_bytes=json.dumps(manifest,sort_keys=True,indent=2).encode()
    trusted=out/'trusted-inventory.json';trusted.write_bytes(trusted_bytes)
    digest=hashlib.sha256(trusted_bytes).hexdigest()
    frozen=out/'frozen-payload';clone_payload(source,frozen,manifest)
    archive=out/'logical-snapshot.zip';archive_payload(frozen,archive,manifest)
    assert not any(name in manifest for name in LOCAL)
    commands=[];cases=[]

    def invoke(data,method,path,body=None):
        parent=data.parent
        (parent/'QUALIFICATION_ONLY').write_text('Restore qualification only')
        env=os.environ.copy()
        for key,child in [('HOME','home'),('USERPROFILE','home'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('TMP','tmp'),('TEMP','tmp'),('TMPDIR','tmp'),('XDG_CACHE_HOME','cache')]:
            directory=parent/child;directory.mkdir(exist_ok=True);env[key]=str(directory)
        env['PYTHONPATH']=str(ROOT);env['ASTROPILOT_DATA_DIR']=str(data)
        env['ASTROPILOT_GUARDIAN_EXPLICIT_RENEWAL']='0'
        command={'method':method,'path':path,'json':body}
        r=subprocess.run([sys.executable,str(Path(seed.__file__).resolve()),'--worker',str(data),json.dumps(command)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=90)
        assert r.returncode==0,(path,r.stderr[-2000:])
        reply=json.loads(r.stdout);commands.append(reply)
        return reply

    def inspect(data):
        project=invoke(data,'GET','/v1/projects/Sh2-129/progress')
        assert project['http']==200,project
        totals={x['acquisition_intent_id']:x['effective_total_seconds'] for x in project['body']['intent_progress_breakdown']}
        assert totals['sh2-129_ha']==5400 and totals['ou4_oiii']==900
        state={} 
        for label,expected in [('ha',5400),('oiii',900)]:
            eid='qualification-execution-'+label
            reply=invoke(data,'GET',f'/v1/executions/{eid}/session')
            assert reply['http']==200,reply
            body=reply['body'];assert body['acquired_after_seconds']==expected and body['credit'] is not None
            state[label]={key:body[key] for key in ('execution','credit','acquired_before_seconds','session_credit_seconds','acquired_after_seconds','current_acquired_seconds','remaining_hours','profile_revision')}
        return state

    source_guardian=invoke(source,'GUARDIAN',None)['body']
    assert source_guardian['state']=='ACTIVE' and source_guardian['owner'] is None
    assert source_guardian['renewal_refusal']=='guardian_session_not_owned'
    # Restore from archive twice, each into a newly allocated destination.
    canonical=None
    for label in ['restore-a','restore-b']:
        data=out/label/'data';restore_archive(archive,data,manifest)
        before=inventory(data);current=inspect(data)
        if canonical is None: canonical=current
        else: assert current==canonical
        for _ in range(2):
            for intent in ('ha','oiii'):
                eid='qualification-execution-'+intent
                reply=invoke(data,'POST',f'/v1/executions/{eid}/intent-progress-credit',{
                    'expected_revision':'CURRENT','evidence_ids':['qualification-evidence-'+intent]})
                assert reply['http']==200 and reply['body']['status']=='already_applied'
        assert inspect(data)==canonical
        assert inventory(data)==before==manifest,'Authoritative bytes changed during replay/readback'
        assert (data/'.outcome_history_cursor.key').is_file()
        if os.name!='nt': assert stat.S_IMODE((data/'.outcome_history_cursor.key').stat().st_mode)==0o600
        assert not (data/'guardian_runtime.json').exists()
        guardian=invoke(data,'GUARDIAN',None)['body']
        assert guardian['state']=='UNKNOWN' and guardian['owner'] is None
        assert guardian['renewal_refusal']=='guardian_session_not_owned'
        assert (data/'.outcome_history_cursor.key').read_bytes()!=(source/'.outcome_history_cursor.key').read_bytes()
        cases.append({'case':label,'result':'PASS','replay':'already_applied','authority_unchanged':True,'local_key_regenerated':True,'guardian_runtime_absent':True})

    def rejected(label,mutate):
        candidate=out/label/'payload';shutil.copytree(frozen,candidate)
        mutate(candidate)
        target=out/label/'data'
        try: clone_payload(candidate,target,manifest)
        except Rejected as e: reason=str(e)
        else: raise AssertionError('Bad snapshot accepted: '+label)
        assert not target.exists()
        cases.append({'case':label,'result':'REJECTED','reason':reason,'destination_created':False})

    execution='execution_lineage/qualification-execution-ha.json'
    rejected('missing-execution',lambda p:(p/execution).unlink())
    rejected('truncated-profile',lambda p:(p/'user_profile.json').write_bytes(b'{'))
    old_profile=source_case/'profile-before-credit.json'
    assert old_profile.is_file()
    rejected('mixed-older-profile',lambda p:shutil.copyfile(old_profile,p/'user_profile.json'))
    rejected('extra-authority',lambda p:(p/'execution_lineage'/'extra.json').write_text('{}'))
    rejected('mutation-after-freeze',lambda p:(p/execution).write_bytes((p/execution).read_bytes()+b' '))
    rejected('unknown-file',lambda p:(p/'unknown.json').write_text('{}'))
    # Simulated source mutation during copy is detected before activation.
    candidate=out/'during-copy'/'payload';shutil.copytree(frozen,candidate)
    original=shutil.copyfile;changed=False
    def interrupted_copy(src,dst,*args,**kwargs):
        nonlocal changed
        result=original(src,dst,*args,**kwargs)
        if not changed:
            changed=True;(candidate/'user_profile.json').write_bytes((candidate/'user_profile.json').read_bytes()+b' ')
        return result
    shutil.copyfile=interrupted_copy
    try:
        try: clone_payload(candidate,out/'during-copy'/'staging',manifest)
        except Rejected: pass
        else: raise AssertionError('Concurrent mutation accepted')
    finally: shutil.copyfile=original
    cases.append({'case':'mutation-during-copy','result':'REJECTED','application_started':False})

    for label,extra in [('zip-case-collision',next(iter(manifest)).upper()),('zip-traversal','../user_profile.json'),('zip-runtime-attestation','guardian_runtime.json')]:
        damaged=out/(label+'.zip');shutil.copyfile(archive,damaged)
        with zipfile.ZipFile(damaged,'a') as z:z.writestr(extra,'{}')
        target=out/label/'data'
        try:restore_archive(damaged,target,manifest)
        except Rejected as e:reason=str(e)
        else:raise AssertionError('Unsafe archive accepted')
        assert not target.exists();cases.append({'case':label,'result':'REJECTED','reason':reason})
    existing=out/'restore-a'/'data';before=inventory(existing)
    try:restore_archive(archive,existing,manifest)
    except Rejected as e:assert str(e)=='destination_exists'
    else:raise AssertionError('Existing destination overwritten')
    assert inventory(existing)==before
    cases.append({'case':'existing-destination','result':'REJECTED','unchanged':True})
    # Deliberate runtime corruption in separate disposable copies, not activation
    # of a manifest-rejected backup. Verify existing read/write refusal boundaries.
    for label,mutation in [('runtime-missing-execution','missing'),('runtime-truncated-execution','truncated'),('runtime-missing-evidence','evidence'),('runtime-wrong-credit','credit')]:
        data=out/label/'data';shutil.copytree(frozen,data)
        if mutation=='missing':(data/execution).unlink()
        elif mutation=='truncated':(data/execution).write_text('{')
        elif mutation=='evidence':
            document=json.loads((data/execution).read_text());document['evidence']=[];(data/execution).write_text(json.dumps(document))
        else:
            path=data/'user_profile.json';profile=json.loads(path.read_text())
            entry=profile['intent_progress_credits']['qualification-execution-ha']
            entry['usable_durations_us']=[900_000_000];entry['total_duration_us']=900_000_000
            path.write_text(json.dumps(profile))
        prior=inventory(data)
        response=invoke(data,'GET','/v1/executions/qualification-execution-ha/session')
        assert response['http'] in (404,503),(label,response)
        project=invoke(data,'GET','/v1/projects/Sh2-129/progress')
        assert project['http']==503 and project['body']['detail']['code']=='project_credit_inconsistent',(label,project)
        revision=json.loads((data/'user_profile.json').read_text())['profile_revision']
        edit=invoke(data,'PUT','/v1/projects/Sh2-129/progress',{'expected_revision':revision,'acquisition_intent_targets':[{'acquisition_intent_id':'sh2-129_ha','target_hours':3}]})
        assert edit['http']==503 and edit['body']['detail']['code']=='project_credit_inconsistent',(label,edit)
        replay=invoke(data,'POST','/v1/executions/qualification-execution-ha/intent-progress-credit',{
            'expected_revision':'CURRENT','evidence_ids':['qualification-evidence-ha']})
        assert replay['http'] in (409,422,503),(label,replay)
        assert inventory(data)==prior
        cases.append({'case':label,'result':'CONTROLLED_REFUSAL','read_http':response['http'],
            'read_code':response['body'].get('detail',{}).get('code'),'project_http':project['http'],'project_edit_http':edit['http'],
            'replay_http':replay['http'],'replay_code':replay['body'].get('detail',{}).get('code'),
            'authority_unchanged':True})
    verify(source,manifest);verify(frozen,manifest,True)
    assert hashlib.sha256(trusted.read_bytes()).hexdigest()==digest
    assert len({r['boot_id'] for r in commands})==len(commands)
    report={'schema_version':1,'result':'PASS','platform':platform.platform(),'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'synthetic_observations':True,'trusted_inventory_sha256':digest,'authority_files':len(manifest),
        'private_reference_used':bool(reference),'private_reference_files':184 if reference else None,
        'fresh_interpreters':len(commands),'cases':cases,'restored_semantic_state':canonical,
        'reference_unchanged':True,'source_authority_unchanged':True,'trusted_inventory_unchanged':True,
        'boundary':'external trusted manifest; not a product restore API or automatic live-copy guarantee'}
    (out/'restore-qualification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','restored_semantic_state')}))

if __name__=='__main__':qualify(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None,sys.argv[3] if len(sys.argv)>3 else None)
