"""Read faults never become empty state or a successful/doubled credit."""
import errno
import json
import logging
from pathlib import Path
import shutil

import pytest

from astropilot.persistence_diagnostics import HEADER
from test_execution_session_api import setup, create_completed, credit


@pytest.mark.parametrize('credited', [False, True])
@pytest.mark.parametrize('store', ['profile', 'execution'])
@pytest.mark.parametrize('fault', ['permission', 'io', 'utf8'])
def test_read_fault_is_explicit_and_recovers_without_loss(tmp_path, monkeypatch, credited, store, fault, caplog):
    caplog.set_level(logging.INFO, logger="astropilot.launcher.persistence")
    source = tmp_path / 'source'
    fresh = setup(source, monkeypatch)
    create_completed(fresh(), 'execution-1', evidence_id='evidence-1')
    if credited:
        assert credit(fresh(), 'execution-1', 'evidence-1', confirm=True).status_code == 200
    source_bytes = {p.relative_to(source): p.read_bytes() for p in source.rglob('*.json')}
    copy = tmp_path / 'copy'
    shutil.copytree(source, copy)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(copy))
    # setup's factory points its execution store at source; create a new one for copy.
    from test_project_progress_restore_consistency import restored_api
    def api():
        return restored_api(copy)
    target = copy / ('user_profile.json' if store == 'profile' else 'execution_lineage/execution-1.json')
    original_open = Path.open
    revision = json.loads(source_bytes[Path('user_profile.json')])['profile_revision']
    body = {'expected_revision': revision, 'evidence_ids':['evidence-1'], 'confirm_historical_baseline':True}
    def failing_open(path, *args, **kwargs):
        if path == target:
            if fault == 'utf8':
                raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'SECRET')
            raise OSError(errno.EACCES if fault == 'permission' else errno.EIO, 'SECRET /private/profile')
        return original_open(path, *args, **kwargs)
    # Construct before injection so UI asset reads are never the fault target.
    client = api()
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', failing_open)
        for route in ['/v1/executions/execution-1/session', '/v1/execution-sessions', '/v1/projects/Sh2-129/progress']:
            response = client.get(route)
            expected = 200 if route.endswith('/progress') and store == 'execution' and not credited else 503
            assert response.status_code == expected, response.text
            assert 'SECRET' not in response.text
        response = client.post('/v1/executions/execution-1/intent-progress-credit', json=body)
        assert response.status_code in (422,503), response.text
        assert 'SECRET' not in response.text
    failures = [json.loads(row.message.split('persistence_diagnostic ',1)[1])
                for row in caplog.records if 'durable_read_failed' in row.message]
    if fault != "utf8" or store == "profile":
        assert failures
    assert all(row['http_status'] == 503 for row in failures)
    if fault != 'utf8' or store == 'profile':
        assert response.headers[HEADER] in {row['diagnostic_id'] for row in failures}
    assert 'SECRET' not in caplog.text
    assert {p.relative_to(copy):p.read_bytes() for p in copy.rglob('*.json')} == source_bytes
    # Recreate application/store instances, as after restart, and recover.
    result = api().post('/v1/executions/execution-1/intent-progress-credit', json=body)
    assert result.status_code == 200, result.text
    assert result.json()['status'] == ('already_applied' if credited else 'applied')
    saved = (copy/'user_profile.json').read_bytes()
    assert credit(api(), 'execution-1', 'evidence-1').json()['status'] == 'already_applied'
    assert (copy/'user_profile.json').read_bytes() == saved
    assert len(json.loads(saved)['intent_progress_credits']) == 1
    assert api().get('/v1/executions/execution-1/session').json()['acquired_after_seconds'] == 5400
    assert {p.relative_to(source):p.read_bytes() for p in source.rglob('*.json')} == source_bytes


@pytest.mark.parametrize('store', ['profile', 'execution'])
@pytest.mark.parametrize('damage', ['missing', 'truncated', 'invalid_utf8'])
def test_damaged_credited_copy_refuses_then_restores_exactly(tmp_path, monkeypatch, store, damage):
    source = tmp_path/'source'
    fresh = setup(source, monkeypatch)
    create_completed(fresh(), 'execution-1', evidence_id='evidence-1')
    assert credit(fresh(), 'execution-1', 'evidence-1', confirm=True).status_code == 200
    original = {p.relative_to(source):p.read_bytes() for p in source.rglob('*.json')}
    copy = tmp_path/'copy'; shutil.copytree(source,copy)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(copy))
    from test_project_progress_restore_consistency import restored_api
    target = copy/('user_profile.json' if store == 'profile' else 'execution_lineage/execution-1.json')
    if damage == 'missing':
        target.unlink()
    else:
        target.write_bytes(b'{' if damage == 'truncated' else b'\xff')
    damaged = {p.relative_to(copy):p.read_bytes() for p in copy.rglob('*.json')}
    api = restored_api(copy)
    for route in ['/v1/executions/execution-1/session','/v1/execution-sessions','/v1/projects/Sh2-129/progress']:
        response = api.get(route)
        assert response.status_code in (404,503), (route,response.text)
    revision = json.loads(original[Path('user_profile.json')])['profile_revision']
    response = api.post('/v1/executions/execution-1/intent-progress-credit',json={
        'expected_revision':revision,'evidence_ids':['evidence-1'],'confirm_historical_baseline':False})
    assert response.status_code in (422,503),response.text
    assert {p.relative_to(copy):p.read_bytes() for p in copy.rglob('*.json')} == damaged
    for path,data in original.items(): (copy/path).write_bytes(data)
    recovered = restored_api(copy)
    assert recovered.get('/v1/executions/execution-1/session').json()['acquired_after_seconds'] == 5400
    for _ in range(3):
        assert credit(restored_api(copy),'execution-1','evidence-1').json()['status'] == 'already_applied'
    assert {p.relative_to(copy):p.read_bytes() for p in copy.rglob('*.json')} == original
    assert {p.relative_to(source):p.read_bytes() for p in source.rglob('*.json')} == original


@pytest.mark.parametrize('missing', ['execution-1', 'execution-2'])
def test_partial_or_mission_history_cannot_hide_a_credited_session(tmp_path, monkeypatch, missing):
    fresh = setup(tmp_path, monkeypatch)
    for number in (1,2):
        create_completed(fresh(), f'execution-{number}', evidence_id=f'evidence-{number}')
        assert credit(fresh(), f'execution-{number}', f'evidence-{number}', confirm=True).status_code == 200
    profile = (tmp_path/'user_profile.json').read_bytes()
    (tmp_path/'execution_lineage'/f'{missing}.json').unlink()
    for route in ['/v1/execution-sessions','/v1/missions/mission-ha/executions']:
        response = fresh().get(route)
        assert response.status_code == 503
        assert response.json()['detail']['code'] == 'session_credit_inconsistent'
    # An unrelated mission is legitimately empty.
    assert fresh().get('/v1/missions/mission-oiii/executions').json() == []
    assert (tmp_path/'user_profile.json').read_bytes() == profile


def test_read_diagnostic_sink_failure_does_not_hide_refusal(tmp_path, monkeypatch):
    from astropilot import persistence_diagnostics
    fresh = setup(tmp_path,monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    before = (tmp_path/'user_profile.json').read_bytes()
    api = fresh(); original = Path.open
    def fail(path,*args,**kwargs):
        if path == tmp_path/'user_profile.json': raise OSError(errno.EIO,'SECRET')
        return original(path,*args,**kwargs)
    def broken(*args,**kwargs): raise OSError('broken diagnostic sink')
    with monkeypatch.context() as patch:
        patch.setattr(Path,'open',fail)
        patch.setattr(persistence_diagnostics._LOGGER,'info',broken)
        result = api.get('/v1/executions/execution-1/session')
    assert result.status_code == 503 and result.headers[HEADER]
    assert (tmp_path/'user_profile.json').read_bytes() == before


@pytest.mark.parametrize('number', [errno.EACCES, errno.EIO])
def test_directory_fault_refuses_history_and_credit_then_recovers(tmp_path,monkeypatch,number):
    import os
    fresh = setup(tmp_path,monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    assert credit(fresh(),'execution-1','evidence-1',confirm=True).status_code == 200
    saved = {p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*.json')}
    revision = json.loads(saved[Path('user_profile.json')])['profile_revision']
    original = os.scandir
    def fail(path):
        if Path(path) == tmp_path/'execution_lineage': raise OSError(number,'SECRET')
        return original(path)
    api = fresh()
    with monkeypatch.context() as patch:
        patch.setattr(os,'scandir',fail)
        result = api.get('/v1/execution-sessions')
        assert result.status_code == 503 and result.headers[HEADER]
        result = api.post('/v1/executions/execution-1/intent-progress-credit',json={
            'expected_revision':revision,'evidence_ids':['evidence-1'],'confirm_historical_baseline':False})
        assert result.status_code == 503 and result.headers[HEADER]
    assert {p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*.json')} == saved
    assert len(fresh().get('/v1/execution-sessions').json()) == 1
    for _ in range(3): assert credit(fresh(),'execution-1','evidence-1').json()['status'] == 'already_applied'
    assert {p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*.json')} == saved
