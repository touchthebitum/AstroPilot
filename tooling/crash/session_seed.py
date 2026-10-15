"""Offline qualification: fresh process for every API command, durable real stores.
Synthetic accepted lineage is seeded via production stores (not acceptance/weather).
Only explicitly supplied sandbox directories are used; no hardware or network.
"""
import os, sys, json, pathlib, subprocess, hashlib, platform, shutil
from uuid import uuid4
BOOT_ID = uuid4().hex
ROOT = pathlib.Path(os.environ["PRODUCT_SOURCE"]).resolve()
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
    # Explicit synthetic UI fixture, independent of live weather or actual equipment.
    from dataclasses import replace
    from datetime import datetime, timezone, date
    from decision.mission.night_planner import NightTask
    fixtures.START = datetime(2026, 10, 15, 20, 0, tzinfo=timezone.utc)
    fixtures.END = fixtures.START + timedelta(hours=4)
    original_mission = fixtures.mission
    def synthetic_mission(**kwargs):
        label = 'Halpha' if kwargs.get('acquisition_intent_id') == 'sh2-129_ha' else 'OIII'
        return replace(original_mission(**kwargs), target='TEST ISOLE Sh2-129 / Ou4 - '+label,
            site_name='COPIE DE TEST', site_timezone='Europe/Zurich',
            tasks=[NightTask('22:00', '22:05', 'TEST UNIQUEMENT', 'Aucune acquisition materielle', 0, 0.0)])
    fixtures.mission = synthetic_mission
    original_context = fixtures.context
    def synthetic_context(*args, **kwargs):
        value = original_context(*args, **kwargs)
        return replace(value, night={**value.night, 'date':date(2026,10,15)})
    fixtures.context = synthetic_context
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
                    selected_at=fixtures.START-timedelta(minutes=15),selected_catalog_key='Sh2-129',selected_imaging_field_id='sh2-129_ou4',selected_acquisition_intent_id=intent),
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
