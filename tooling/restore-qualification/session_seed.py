"""Offline qualification: fresh process for every API command, durable real stores.
Synthetic accepted lineage is seeded via production stores (not acceptance/weather).
Only explicitly supplied sandbox directories are used; no hardware or network.
"""
import os, sys, json, pathlib, subprocess, hashlib, platform, shutil
from uuid import uuid4
BOOT_ID = uuid4().hex
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

def worker(data, command):
    data = pathlib.Path(data).resolve()
    assert data.name == 'data' and (data.parent / 'QUALIFICATION_ONLY').is_file()
    os.environ['ASTROPILOT_DATA_DIR'] = str(data)
    import socket
    def forbidden(*a, **k): raise AssertionError('Network forbidden in qualification')
    # Windows asyncio creates an internal numeric loopback socket pair.
    # Permit that plumbing while still refusing every external connection.
    original_connect = socket.socket.connect
    import ipaddress
    def connect_loopback(sock, address):
        if isinstance(address, tuple) and isinstance(address[0], str):
            try: local = ipaddress.ip_address(address[0]).is_loopback
            except ValueError: local = False
            if local: return original_connect(sock, address)
        return forbidden()
    socket.socket.connect = connect_loopback
    socket.create_connection = forbidden
    from datetime import timedelta
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from astropilot.app import create_app
    from astropilot.launcher import _configure_launcher_logger
    _configure_launcher_logger(log_path=data / 'Logs' / 'AstroPilot.log')
    from astropilot.user_profile import load_user_profile, save_user_profile
    from astropilot.execution_lineage_store import FileExecutionLineageStore
    from astropilot.decision_acceptance_lineage_store import FileDecisionAcceptanceLineageStore
    from decision.services.durable_tonight_application_service import DurableTonightApplicationService
    import importlib.util
    spec = importlib.util.spec_from_file_location('lineage_fixture', ROOT / 'tests/architecture/test_decision_acceptance_lineage_persistence.py')
    fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)
    lineage = FileDecisionAcceptanceLineageStore(data / 'decision_lineage')
    with TestClient(create_app(guardian_renewal_enabled=False), raise_server_exceptions=False) as api:
        if command['method'] == 'INIT':
            r = api.put('/v1/configuration', json={'expected_revision':load_user_profile()['profile_revision'] if (data/'user_profile.json').exists() else 0,'site':{'name':'Qualification only','latitude':46.9,'longitude':6.6,'bortle':4},
                'equipment':{'preset_id':'samyang_183'}, 'projects':{'Sh2-129':{'hours':2,'target_hours':20,'importance':9}}})
            assert r.status_code == 200, r.text
            r = api.put('/v1/projects/Sh2-129/progress', json={'expected_revision':load_user_profile()['profile_revision'],
                'imaging_field_id':'sh2-129_ou4', 'acquisition_intent_progress':[{'acquisition_intent_id':'sh2-129_ha','acquired_duration_manual':3600}],
                'acquisition_intent_targets':[{'acquisition_intent_id':'sh2-129_ha','target_hours':2}, {'acquisition_intent_id':'ou4_oiii','target_hours':2}]})
            assert r.status_code == 200, r.text
            for label,intent in [('ha','sh2-129_ha'),('oiii','ou4_oiii')]:
                did,sid,mid = [f'qualification-{x}-{label}' for x in ('decision','selection','mission')]
                lineage.create_context(fixtures.context(did))
                lineage.commit_selection_and_mission(fixtures.selection(selection_id=sid,decision_id=did,
                    selected_catalog_key='Sh2-129',selected_imaging_field_id='sh2-129_ou4',selected_acquisition_intent_id=intent),
                    fixtures.mission(mission_id=mid,decision_id=did,selection_id=sid,imaging_field_id='sh2-129_ou4',acquisition_intent_id=intent))
            return {'http':200,'body':{'seeded_synthetic_accepted_lineage':True},'pid':os.getpid(), 'boot_id':BOOT_ID}
        if command['method']=='GUARDIAN':
            from datetime import datetime, timezone
            from astropilot.app import _production_service_factory
            from astropilot.guardian_session_lifecycle import GuardianSessionLifecycle
            from astropilot.guardian_session_store import GuardianSessionStore
            store=GuardianSessionStore(data/'guardian_runtime.json')
            now=datetime.now(timezone.utc)
            evidence=store.read(now)
            caller=GuardianSessionLifecycle(_production_service_factory(),store)
            try:caller.renew('qualification-execution-ha',observed_at=now)
            except ValueError as error: reason=str(error)
            else:raise AssertionError('Renewal ownership restored from disk')
            return {'http':200,'body':{'state':evidence.state.value if evidence else 'UNKNOWN',
                'owner':caller.owner_execution_id,'renewal_refusal':reason},'pid':os.getpid(),'boot_id':BOOT_ID}
        payload=command.get('json')
        if isinstance(payload,dict) and payload.get('expected_revision')=='CURRENT':
            payload['expected_revision']=load_user_profile()['profile_revision']
        if command.get('inject_write_failure'):
            original = pathlib.Path.replace
            def fail_replace(path, target):
                if pathlib.Path(target).name == 'user_profile.json':
                    raise OSError('QUALIFICATION simulated profile write failure')
                return original(path, target)
            pathlib.Path.replace = fail_replace
        r=api.request(command['method'],command['path'],json=payload)
        return {'http':r.status_code,'body':r.json() if 'application/json' in r.headers.get('content-type','') else {'non_json_error':r.text},'pid':os.getpid(), 'boot_id':BOOT_ID, 'diagnostic_id':r.headers.get('X-Persistence-Diagnostic-ID')}

def inventory(directory, include_logs=True):
    return {str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file() and (include_logs or p.relative_to(directory).parts[0] != 'Logs')}

def qualify(destination, reference=None):
    destination=pathlib.Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'QUALIFICATION_ONLY').write_text('Synthetic session evidence; never real acquisition.\n')
    data=destination/'data'; data.mkdir()
    before=None
    if reference:
        reference=pathlib.Path(reference).resolve()
        assert reference!=data and reference not in data.parents
        before=inventory(reference)
        shutil.copytree(reference,data,dirs_exist_ok=True)
        # Local cursor signing state is explicitly outside logical history backups.
        for name in ('.outcome_history_cursor.key','.outcome_history_cursor.key.lock'):
            (data/name).unlink(missing_ok=True)
    results=[]
    env=os.environ.copy()
    for key,child in [('HOME','home'),('USERPROFILE','home'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('XDG_CACHE_HOME','cache'),('TMP','tmp'),('TEMP','tmp'),('TMPDIR','tmp')]:
        p=destination/child;p.mkdir(exist_ok=True);env[key]=str(p)
    env['ASTROPILOT_DATA_DIR']=str(data);env['PYTHONPATH']=str(ROOT)
    def call(name,method,path=None,body=None,status=200,inject_write_failure=False):
        cmd={'method':method,'path':path,'json':body,'inject_write_failure':inject_write_failure}
        r=subprocess.run([sys.executable,str(pathlib.Path(__file__).resolve()),'--worker',str(data),json.dumps(cmd)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=90)
        assert r.returncode==0, (name,r.stderr,r.stdout[-1000:])
        result=json.loads(r.stdout);results.append({'step':name,**result})
        assert result['http']==status,(name,result)
        return result['body']
    call('initialize copied profile and synthetic accepted lineage','INIT')
    (destination/'profile-before-credit.json').write_bytes((data/'user_profile.json').read_bytes())
    start='2026-10-15T20:00:00+00:00';end='2026-10-15T21:00:00+00:00'
    for label,seconds in [('ha',1800),('oiii',900)]:
        eid=f'qualification-execution-{label}';mid=f'qualification-mission-{label}';evidence=f'qualification-evidence-{label}'
        base={'execution_id':eid,'mission_id':mid}
        creation=call(label+' create','POST','/v1/executions',base)
        call(label+' identical create replay','POST','/v1/executions',base)
        transition={**base,'status':'in_progress','actual_start':start,'actual_end':None,'actual_duration':None}
        call(label+' start','POST','/v1/execution-transitions',transition)
        call(label+' duplicate start refused','POST','/v1/execution-transitions',transition,status=409)
        state=call(label+' read after process restart','GET',f'/v1/executions/{eid}/session')
        assert state['execution']['status']=='in_progress' and state['credit'] is None
        credit={'expected_revision':'CURRENT','evidence_ids':[evidence],'confirm_historical_baseline':False}
        call(label+' credit before completion refused','POST',f'/v1/executions/{eid}/intent-progress-credit',credit,status=422)
        transition.update(status='completed',actual_end=end,actual_duration=3600)
        call(label+' close','POST','/v1/execution-transitions',transition)
        call(label+' duplicate close refused','POST','/v1/execution-transitions',transition,status=409)
        call(label+' missing evidence refused','POST',f'/v1/executions/{eid}/intent-progress-credit',credit,status=422)
        observation={'evidence_id':evidence,'execution_id':eid,'category':'acquisition','observed_at':end,'source':'user','usable_integration_duration':seconds}
        call(label+' synthetic integration evidence','POST','/v1/outcome-evidence',observation)
        call(label+' identical evidence replay','POST','/v1/outcome-evidence',observation)
        call(label+' conflicting evidence refused','POST','/v1/outcome-evidence',{**observation,'usable_integration_duration':seconds+60},status=409)
        if label=='ha':
            refused=call(label+' baseline confirmation required','POST',f'/v1/executions/{eid}/intent-progress-credit',credit,status=409)
            assert refused['detail']['code']=='intent_progress_baseline_confirmation_required'
            credit['confirm_historical_baseline']=True
        snapshot=inventory(data, include_logs=False)
        failure=call(label+' profile write failure visible','POST',f'/v1/executions/{eid}/intent-progress-credit',credit,status=503,inject_write_failure=True)
        assert failure['detail']['code']=='intent_progress_persistence_unavailable'
        assert failure['detail']['category']=='io_error'
        assert inventory(data, include_logs=False)==snapshot,'Failed write must preserve persistent data'
        state=call(label+' no credit after failed write and restart','GET',f'/v1/executions/{eid}/session')
        assert state['credit'] is None
        applied=call(label+' credit','POST',f'/v1/executions/{eid}/intent-progress-credit',credit)
        assert applied['status']=='applied'
        snapshot=inventory(data, include_logs=False)
        replay=call(label+' credit replay after restart','POST',f'/v1/executions/{eid}/intent-progress-credit',credit)
        assert replay['status']=='already_applied'
        assert inventory(data, include_logs=False)==snapshot,'Replay must not write persistent data'
        state=call(label+' reconstructed credited session','GET',f'/v1/executions/{eid}/session')
        assert state['session_credit_seconds']==seconds
        assert len(state['evidence'])==1
        assert state['acquired_after_seconds']==(3600 if label=='ha' else 0)+seconds
        progress=call(label+' reconstructed progress','GET','/v1/projects/Sh2-129/progress')
        item=next(i for i in progress['intent_progress_breakdown'] if i['acquisition_intent_id']==('sh2-129_ha' if label=='ha' else 'ou4_oiii'))
        assert item['effective_total_seconds']==(3600 if label=='ha' else 0)+seconds
    eid='qualification-interrupted';mid='qualification-mission-ha'
    base={'execution_id':eid,'mission_id':mid}
    call('interrupted create','POST','/v1/executions',base)
    call('interrupted start','POST','/v1/execution-transitions',{**base,'status':'in_progress','actual_start':start,'actual_end':None,'actual_duration':None})
    call('interrupted close','POST','/v1/execution-transitions',{**base,'status':'interrupted','actual_start':start,'actual_end':end,'actual_duration':3600})
    evidence={'evidence_id':'qualification-interrupted-evidence','execution_id':eid,'category':'acquisition','observed_at':end,'source':'user','usable_integration_duration':600}
    call('interrupted synthetic evidence','POST','/v1/outcome-evidence',evidence)
    refused=call('interrupted credit refused','POST',f'/v1/executions/{eid}/intent-progress-credit',{'expected_revision':'CURRENT','evidence_ids':[evidence['evidence_id']]},status=422)
    assert refused['detail']['code']=='execution_not_completed'
    state=call('interrupted persists without credit','GET',f'/v1/executions/{eid}/session')
    assert state['execution']['status']=='interrupted' and state['credit'] is None
    # A fresh process discovers both persisted sessions and no duplicate evidence/credits.
    sessions=call('all sessions after restart','GET','/v1/execution-sessions')
    assert len(sessions)==3
    assert len(json.loads((data/'user_profile.json').read_text())['intent_progress_credits'])==2
    assert len({r['boot_id'] for r in results})==len(results),'Each invocation must have a new interpreter boot identity'
    # The OS may legitimately reuse a PID after the previous child exited.
    if reference: assert inventory(reference)==before,'Reference changed'
    persistence_events=[json.loads(line.split('persistence_diagnostic ',1)[1]) for line in (data/'Logs'/'AstroPilot.log').read_text(encoding='utf-8').splitlines() if 'persistence_diagnostic ' in line]
    correlated=[row for row in results if row.get('diagnostic_id') and row['http'] in (200,503)]
    assert len(correlated)==len(persistence_events)==6
    assert [e['diagnostic_id'] for e in persistence_events]==[r['diagnostic_id'] for r in correlated]
    assert len({e['diagnostic_id'] for e in persistence_events})==6
    assert [e['category'] for e in persistence_events]==['io_error','applied','already_applied']*2
    report={'persistence_events':persistence_events,'schema_version':1,'platform':platform.platform(),'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'synthetic':True,'reference_unchanged':True if reference else None,'reference_files':len(before) if before else None,
        'fresh_processes':len(results),'result':'PASS','steps':results}
    (destination/'qualification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='steps'}))

if __name__=='__main__':
    if sys.argv[1]=='--worker': print(json.dumps(worker(sys.argv[2],json.loads(sys.argv[3]))))
    else: qualify(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None)
