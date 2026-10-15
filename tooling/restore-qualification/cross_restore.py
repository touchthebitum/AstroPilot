"""Restore the other CI platform's synthetic snapshot; no private profile inputs."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import stat
import qualify_restore as protocol
import session_seed as seed


def qualify(out,artifact):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    artifact=Path(artifact).resolve()
    report_path=next(artifact.rglob('restore-qualification.json'))
    sender=json.loads(report_path.read_text())
    assert sender['result']=='PASS' and sender['source_sha']=='435db8ab800e13021eefd7a85f3516ab14a9d051'
    assert not sender['private_reference_used']
    trusted=next(artifact.rglob('trusted-inventory.json'))
    archive=next(artifact.rglob('logical-snapshot.zip'))
    frozen_hash=hashlib.sha256(trusted.read_bytes()).hexdigest()
    assert frozen_hash==sender['trusted_inventory_sha256']
    manifest=json.loads(trusted.read_text());assert not any(name in manifest for name in protocol.LOCAL)
    archive_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
    data=out/'data';protocol.restore_archive(archive,data,manifest)
    (out/'QUALIFICATION_ONLY').write_text('Cross-platform synthetic qualification only')
    assert not (data/'.outcome_history_cursor.key').exists()
    replies=[]
    def invoke(method,path,body=None):
        env=os.environ.copy()
        for key,child in [('HOME','home'),('USERPROFILE','home'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('TMP','tmp'),('TEMP','tmp'),('TMPDIR','tmp'),('XDG_CACHE_HOME','cache')]:
            p=out/child;p.mkdir(exist_ok=True);env[key]=str(p)
        env['PYTHONPATH']=str(protocol.ROOT);env['ASTROPILOT_DATA_DIR']=str(data)
        env['ASTROPILOT_GUARDIAN_EXPLICIT_RENEWAL']='0'
        r=subprocess.run([sys.executable,str(Path(seed.__file__).resolve()),'--worker',str(data),json.dumps({'method':method,'path':path,'json':body})],cwd=protocol.ROOT,env=env,capture_output=True,text=True,timeout=90)
        assert r.returncode==0,r.stderr[-2000:]
        reply=json.loads(r.stdout);replies.append(reply);assert reply['http']==200,reply
        return reply['body']
    totals={}
    for label,expected in [('ha',5400),('oiii',900)]:
        eid='qualification-execution-'+label
        before=invoke('GET',f'/v1/executions/{eid}/session')
        for _ in range(3):
            result=invoke('POST',f'/v1/executions/{eid}/intent-progress-credit',{'expected_revision':'CURRENT','evidence_ids':['qualification-evidence-'+label]})
            assert result['status']=='already_applied'
        after=invoke('GET',f'/v1/executions/{eid}/session')
        assert after['credit']==before['credit'] and after['profile_revision']==before['profile_revision']
        assert after['acquired_after_seconds']==before['acquired_after_seconds']==expected
        totals[label]=expected
    guardian=invoke('GUARDIAN',None)
    assert guardian['state']=='UNKNOWN' and guardian['owner'] is None
    assert guardian['renewal_refusal']=='guardian_session_not_owned'
    protocol.verify(data,manifest)
    assert len(json.loads((data/'user_profile.json').read_text())['intent_progress_credits'])==2
    assert (data/'.outcome_history_cursor.key').is_file()
    if os.name!='nt':assert stat.S_IMODE((data/'.outcome_history_cursor.key').stat().st_mode)==0o600
    assert hashlib.sha256(trusted.read_bytes()).hexdigest()==frozen_hash
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==archive_hash
    assert len({r['boot_id'] for r in replies})==len(replies)==11
    result={'result':'PASS','product_sha':sender['source_sha'],'sender_platform':sender['platform'],
        'receiver_platform':platform.platform(),'trusted_inventory_sha256':frozen_hash,
        'archive_sha256':archive_hash,'authority_files':len(manifest),'fresh_interpreters':len(replies),
        'replay_status':'already_applied','totals_seconds':totals,'authority_unchanged':True,
        'guardian_owner_restored':False,'local_signing_key_regenerated':True,'synthetic_only':True}
    (out/'cross-restore-qualification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=='__main__':qualify(sys.argv[1],sys.argv[2])
