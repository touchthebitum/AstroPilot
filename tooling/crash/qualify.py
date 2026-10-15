"""Public fixtures, real production stores/API, killed children and fresh-process recovery."""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import time

SOURCE=Path(os.environ['PRODUCT_SOURCE']).resolve()
SHA='ee5df1456d0a60e9149ae792efc601e8e57f7c68'
WORKER=Path(__file__).with_name('worker.py')
# Windows venv python.exe can be a redirector. Launch the actual interpreter
# directly, adding this locked venv's packages before loading our test worker.
INTERPRETER=str(Path(getattr(sys,'_base_executable',sys.executable)).resolve())
BOOTSTRAP="import runpy,site,sys;site.addsitedir(sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
def child_command(data,command):
    return [INTERPRETER,'-c',BOOTSTRAP,sysconfig.get_paths()['purelib'],str(WORKER),str(data),json.dumps(command)]

def inventory(root,logical=False):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()
            and (not logical or (p.suffix=='.json' and p.relative_to(root).parts[0]!='Logs'))}

def env_for(case):
    env={k:v for k,v in os.environ.items() if not k.startswith(('ASTROPILOT_','NIGHTMERIT_','FIELD_LAB_'))}
    for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TMP','TEMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME'):
        path=case/'environment'/key;path.mkdir(parents=True,exist_ok=True);env[key]=str(path)
    env.update(PRODUCT_SOURCE=str(SOURCE),PYTHONPATH=str(SOURCE),ASTROPILOT_DATA_DIR=str(case/'data'))
    return env

def request(case,method,path=None,body=None):
    command={'method':method,'path':path,'json':body}
    child=subprocess.run(child_command(case/'data',command),
        cwd=SOURCE,env=env_for(case),text=True,capture_output=True,timeout=90)
    assert child.returncode==0,(child.returncode,child.stderr,child.stdout)
    result=json.loads(child.stdout)
    assert result['http']==200,result
    return result

def credit_body(label):
    return {'expected_revision':'CURRENT','evidence_ids':['crash-evidence-'+label],
            'confirm_historical_baseline':True}

def route(label): return '/v1/executions/crash-execution-'+label+'/intent-progress-credit'

def make_case(path,source=None):
    path.mkdir(parents=True,exist_ok=False)
    (path/'QUALIFICATION_ONLY').write_text('PUBLIC SYNTHETIC CRASH QUALIFICATION ONLY',encoding='utf-8')
    if source: shutil.copytree(source/'data',path/'data')
    else: (path/'data').mkdir()
    return path

def qualify(output):
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()==SHA
    assert not subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=SOURCE,text=True).strip()
    output.mkdir(parents=True,exist_ok=False)
    base=make_case(output/'uncredited')
    identity_code="import json,os;print(json.dumps({'pid':os.getpid(),'parent_pid':os.getppid()}))"
    probe=subprocess.Popen([sys.executable,'-c',identity_code],env=env_for(base),stdout=subprocess.PIPE,text=True)
    probe_output,_=probe.communicate(timeout=30)
    assert probe.returncode==0
    launcher_probe={'spawned_pid':probe.pid,**json.loads(probe_output)}
    calls=[]
    def call(*args,**kwargs):
        result=request(*args,**kwargs);calls.append({'boot_id':result['boot_id'],'pid':result['pid'],'case':args[0].name,'method':args[1],'path':args[2] if len(args)>2 else None,'http':result['http']});return result['body']
    call(base,'INIT')
    for label,seconds in [('ha',1800),('oiii',900)]:
        eid='crash-execution-'+label;mid='qualification-mission-'+label
        call(base,'POST','/v1/executions',{'execution_id':eid,'mission_id':mid})
        transition={'execution_id':eid,'mission_id':mid,'status':'in_progress',
                    'actual_start':'2026-10-15T20:00:00+00:00','actual_end':None,'actual_duration':None}
        call(base,'POST','/v1/execution-transitions',transition)
        transition.update(status='completed',actual_end='2026-10-15T21:00:00+00:00',actual_duration=3600)
        call(base,'POST','/v1/execution-transitions',transition)
        call(base,'POST','/v1/outcome-evidence',{'execution_id':eid,'evidence_id':'crash-evidence-'+label,
            'category':'acquisition','observed_at':'2026-10-15T21:00:00+00:00','source':'user',
            'usable_integration_duration':seconds})
    pending={}
    for target,other in [('ha','oiii'),('oiii','ha')]:
        pending[target]=make_case(output/(target+'-pending'),base)
        assert call(pending[target],'POST',route(other),credit_body(other))['status']=='applied'
    both=make_case(output/'both-credited',pending['ha'])
    assert call(both,'POST',route('ha'),credit_body('ha'))['status']=='applied'
    snapshots={name:inventory(case/'data') for name,case in [('ha',pending['ha']),('oiii',pending['oiii']),('both',both)]}
    cases=[]
    for label in ('ha','oiii'):
      for stage in ('partial_temp','before_replace','after_replace','after_response','replay_after_load','replay_response'):
        replay=stage.startswith('replay')
        source=both if replay else pending[label]
        case=make_case(output/(label+'-'+stage),source)
        before=inventory(case/'data',True)
        profile_before=json.loads((case/'data/user_profile.json').read_text(encoding='utf-8'))
        command={'method':'POST','path':route(label),'json':credit_body(label),'crash_stage':stage}
        with (case/'stdout.log').open('w',encoding='utf-8') as stdout,(case/'stderr.log').open('w',encoding='utf-8') as stderr:
          child=subprocess.Popen(child_command(case/'data',command),
            cwd=SOURCE,env=env_for(case),stdout=stdout,stderr=stderr)
          try:
            deadline=time.monotonic()+90
            marker=case/'suspended.json'
            while not marker.exists():
                assert child.poll() is None,('child exited before suspension',case.name,child.returncode)
                assert time.monotonic()<deadline,('suspension timeout',case.name)
                time.sleep(.05)
            reached=json.loads(marker.read_text(encoding='utf-8'))
            assert reached['pid']==child.pid and reached['stage']==stage,(reached,child.pid)
            assert reached['parent_pid']==os.getpid(),reached
            assert child.poll() is None
            child.kill();code=child.wait(timeout=30)
            assert code!=0,code
          finally:
            if child.poll() is None:child.kill();child.wait(timeout=30)
        # No result was delivered by the deliberately killed request process.
        assert not (case/'stdout.log').read_text(encoding='utf-8').strip()
        after_kill=inventory(case/'data',True)
        disk=json.loads((case/'data/user_profile.json').read_text(encoding='utf-8'))
        eid='crash-execution-'+label
        committed=stage in ('after_replace','after_response') or replay
        assert (eid in disk.get('intent_progress_credits',{}))==committed
        other='crash-execution-'+('oiii' if label=='ha' else 'ha')
        assert disk['intent_progress_credits'][other]==profile_before['intent_progress_credits'][other]
        assert disk['profile_revision']==profile_before['profile_revision']+(0 if replay or not committed else 1)
        assert {k:v for k,v in after_kill.items() if k!='user_profile.json'}=={k:v for k,v in before.items() if k!='user_profile.json'}
        if not committed or replay:assert after_kill==before
        session=call(case,'GET','/v1/executions/'+eid+'/session')
        assert (session['credit'] is not None)==committed
        recovered=call(case,'POST',route(label),credit_body(label))
        assert recovered['status']==('already_applied' if committed else 'applied')
        stable=inventory(case/'data',True)
        for _ in range(3):assert call(case,'POST',route(label),credit_body(label))['status']=='already_applied'
        for intent,total in [('ha',5400),('oiii',900)]:
            session=call(case,'GET','/v1/executions/crash-execution-'+intent+'/session')
            assert session['acquired_after_seconds']==total
        assert call(case,'GET','/v1/projects/Sh2-129/progress')['profile_revision']==disk['profile_revision']+(0 if committed else 1)
        assert inventory(case/'data',True)==stable
        final=json.loads((case/'data/user_profile.json').read_text(encoding='utf-8'))
        assert len(final['intent_progress_credits'])==2
        assert final['intent_progress_credits'][other]==profile_before['intent_progress_credits'][other]
        cases.append({'intent':label,'stage':stage,'killed_process':reached,'exit_code':code,
            'committed_before_restart':committed,'recovery_status':recovered['status'],
            'ha_seconds':5400,'oiii_seconds':900,'credit_count':2,'replay_mutated':False,
            'temporary_residue_count':len(list((case/'data').glob('.user_profile.*.tmp'))),
            'before':before,'after_kill':after_kill,'after_replay':stable})
    for name,case in [('ha',pending['ha']),('oiii',pending['oiii']),('both',both)]:
        assert inventory(case/'data')==snapshots[name],name
    boots=[x['boot_id'] for x in calls]+[x['killed_process']['boot_id'] for x in cases]
    assert len(boots)==len(set(boots))
    proof={'result':'PASS','product_sha':SHA,'os':platform.platform(),'python':platform.python_version(),
           'legacy_launcher_probe':launcher_probe,'cases':cases,'requests':calls,'source_snapshot_inventories':snapshots,'fresh_process_count':len(boots),'source_snapshots_unchanged':True,
           'real_profile_used':False,'source_diff_empty':True,'instrumentation':'test only; parent kill/TerminateProcess',
           'limits':['not power loss','not packaged UI','credit profile persistence boundary']}
    (output/'crash-qualification.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in proof.items() if k!='cases'}))

if __name__=='__main__':qualify(Path(sys.argv[1]).resolve())
