"""HTTP integration and deterministic command/publication races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.guardian_renewal_api import GuardianRenewalAdapter, VERSION
from astropilot.guardian_session_store import GuardianSessionStore
from decision.models.execution import Execution, ExecutionStatus as Status
from decision.models.guardian import GuardianSessionState as State
from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from decision.services.execution_outcome_application import ExecutionOutcomeApplicationService

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


class Clock:
    value = NOW
    def __call__(self):
        return self.value


def service():
    result = ExecutionOutcomeApplicationService(mission_loader=lambda _: None)
    for name in ['one', 'two']:
        result.lineage_store.create_execution(Execution(name, 'mission', Status.NOT_STARTED, None, None, None))
    return result


def body(instance):
    return dict(schema_version=VERSION, confirmation='USER_CONFIRMS_ACQUISITION_CONTINUES', owner_instance_id=instance)


def transition(status='in_progress', execution_id='one'):
    return dict(execution_id=execution_id, mission_id='mission', status=status,
        actual_start=NOW.isoformat(), actual_end=(NOW + timedelta(seconds=60)).isoformat() if status != 'in_progress' else None,
        actual_duration=60 if status != 'in_progress' else None)


@pytest.fixture
def env(tmp_path):
    clock, svc = Clock(), service()
    app = create_app(service_factory=lambda: svc, clock=clock, guardian_renewal_enabled=True,
                     guardian_attestation_path=tmp_path / 'session.json')
    with TestClient(app) as api:
        adapter = app.state.guardian_renewal
        yield api, adapter, svc, clock


def start(env):
    api, adapter, _, _ = env
    key = str(uuid4())
    result = api.post('/v1/execution-transitions', json=transition(), headers={
        'Idempotency-Key': key, 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id})
    assert result.status_code == 200, result.text
    return key


def renew(env, *, key=None, execution_id='one', instance=None, payload=None):
    api, adapter, _, _ = env
    return api.post(f'/v1/executions/{execution_id}/guardian-renewal',
        json=payload or body(instance or adapter.owner_instance_id), headers={'Idempotency-Key': key or str(uuid4())})


def test_disabled_and_legacy_transition(tmp_path):
    svc = service()
    with TestClient(create_app(service_factory=lambda: svc, clock=lambda: NOW)) as api:
        assert api.post('/v1/execution-transitions', json=transition()).status_code == 200
        r = api.post('/v1/executions/one/guardian-renewal', json=body('old'), headers={'Idempotency-Key': str(uuid4())})
        assert r.status_code == 409 and r.json()['code'] == 'guardian_mode_disabled'
        assert r.headers['cache-control'] == 'no-store'
        status = api.get('/v1/executions/one/guardian-renewal').json()
        assert not status['guardian_mode_enabled'] and not status['renewal_eligible']
        assert not list(tmp_path.iterdir())


def test_startup_lock_and_config(tmp_path, monkeypatch):
    path = tmp_path / 'session.json'
    first = GuardianRenewalAdapter(service(), path, lambda: NOW)
    try:
        with pytest.raises(RuntimeError, match='exclusivity'):
            GuardianRenewalAdapter(service(), path, lambda: NOW)
    finally:
        first.close()
    second = GuardianRenewalAdapter(service(), path, lambda: NOW)
    second.close()
    for config in [dict(guardian_attestation_path=None), dict(guardian_attestation_path='relative')]:
        with pytest.raises(RuntimeError):
            with TestClient(create_app(service_factory=service, guardian_renewal_enabled=True, **config)):
                pass
    monkeypatch.setenv('WEB_CONCURRENCY', '2')
    with pytest.raises(RuntimeError, match='single_worker'):
        with TestClient(create_app(service_factory=service, guardian_renewal_enabled=True, guardian_attestation_path=path)):
            pass


def test_success_replay_conflict_and_no_double_transition(env, monkeypatch):
    api, adapter, svc, clock = env
    calls = []
    original = svc.transition_execution
    def counted(destination):
        calls.append(destination)
        return original(destination)
    monkeypatch.setattr(svc, 'transition_execution', counted)
    start_key = start(env)
    repeated = api.post('/v1/execution-transitions', json=transition(), headers={
        'Idempotency-Key': start_key, 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id})
    assert repeated.status_code == 200 and len(calls) == 1
    clock.value += timedelta(seconds=30)
    key = str(uuid4())
    r = renew(env, key=key)
    assert r.status_code == 200 and not r.json()['replayed']
    original_bytes = adapter.store.path.read_bytes()
    clock.value += timedelta(seconds=1000)
    replay = renew(env, key=key)
    assert replay.status_code == 200 and replay.json()['replayed']
    assert replay.json()['confirmed_at'] == r.json()['confirmed_at']
    assert adapter.store.path.read_bytes() == original_bytes and len(calls) == 1
    assert renew(env, key=key, execution_id='two').json()['code'] == 'guardian_idempotency_conflict'
    assert renew(env, key=key, instance='changed').json()['code'] == 'guardian_owner_instance_mismatch'
    assert not api.get('/v1/executions/one/guardian-renewal').json()['renewal_eligible']


@pytest.mark.parametrize('change,expected', [
    ('missing', 'guardian_session_attestation_lost'), ('corrupt', 'guardian_session_attestation_lost'),
    ('inactive', 'guardian_session_attestation_lost'), ('other', 'guardian_session_attestation_lost'),
    ('future', 'guardian_session_attestation_lost'), ('expired', 'guardian_session_attestation_lost'),
    ('closed', 'guardian_execution_not_in_progress'),
])
def test_lost_evidence_and_ineligible_execution(env, change, expected):
    api, adapter, svc, clock = env
    start(env)
    if change == 'missing': adapter.store.path.unlink()
    elif change == 'corrupt': adapter.store.path.write_text('private/path invalid')
    elif change == 'expired': clock.value += timedelta(seconds=901)
    elif change == 'closed':
        svc.transition_execution(Execution('one', 'mission', Status.COMPLETED, NOW, NOW + timedelta(seconds=60), timedelta(seconds=60)))
    else:
        adapter.store.write(GuardianLiveSessionEvidence(
            State.INACTIVE if change == 'inactive' else State.ACTIVE,
            NOW + timedelta(seconds=1) if change == 'future' else NOW,
            'caller_session_heartbeat_v1', 'CALLER_ASSERTED', 'two' if change == 'other' else 'one'))
    r = renew(env)
    assert r.status_code == 409 and r.json()['code'] == expected
    assert r.json()['execution_commit'] == 'not_attempted'
    assert adapter.lifecycle.owner_execution_id is None
    assert 'private/path' not in r.text


def test_wrong_instance_id_and_not_owned_preserve_owner(env):
    start(env)
    assert renew(env, instance='old').json()['code'] == 'guardian_owner_instance_mismatch'
    assert renew(env, execution_id='absent').status_code == 404
    assert renew(env, execution_id='two').json()['code'] == 'guardian_session_not_owned'
    assert env[1].lifecycle.owner_execution_id == 'one'


@pytest.mark.parametrize('payload', [dict(), {**body('x'), 'ttl': 900}, {**body('x'), 'confirmation': 'yes'}])
def test_strict_schema(env, payload):
    r = env[0].post('/v1/executions/one/guardian-renewal', json=payload, headers={'Idempotency-Key': str(uuid4())})
    assert r.status_code == 422 and r.json()['code'] == 'invalid_guardian_renewal_request'
    assert not env[1].store.path.exists()


def test_missing_key_and_transition_guard_and_origin(env):
    api, adapter, _, _ = env
    assert api.post('/v1/executions/one/guardian-renewal', json=body(adapter.owner_instance_id)).status_code == 422
    assert api.post('/v1/execution-transitions', json=transition()).status_code == 422
    assert api.post('/v1/executions/one/guardian-renewal', json=body(adapter.owner_instance_id),
        headers={'Origin': 'https://evil.test', 'Idempotency-Key': str(uuid4())}).status_code == 422


def test_read_only_get_and_restart(env):
    api, adapter, svc, clock = env
    start(env)
    payload = adapter.store.path.read_bytes()
    clock.value += timedelta(seconds=901)
    for _ in range(2):
        assert not api.get('/v1/executions/one/guardian-renewal').json()['renewal_eligible']
    assert adapter.store.path.read_bytes() == payload
    assert adapter.lifecycle.owner_execution_id == 'one'
    old = adapter.owner_instance_id
    adapter.close()
    replacement = GuardianRenewalAdapter(svc, adapter.store.path, clock)
    try:
        assert replacement.owner_instance_id != old
        assert replacement.command('renew', 'one', str(uuid4()), old, 'same', clock.value)[1]['code'] == 'guardian_owner_instance_mismatch'
        assert replacement.command('renew', 'one', str(uuid4()), replacement.owner_instance_id, 'same', clock.value)[1]['code'] == 'guardian_session_not_owned'
        assert adapter.store.path.read_bytes() == payload
    finally:
        replacement.close()


def test_receipt_expired_out_of_order_boundary_and_backward(env):
    _, adapter, _, clock = env
    start(env)
    clock.value += timedelta(seconds=900)
    assert renew(env).status_code == 200
    before = adapter.store.path.read_bytes()
    r = adapter.command('renew', 'one', str(uuid4()), adapter.owner_instance_id, 'x', NOW + timedelta(seconds=899))
    assert r[1]['code'] == 'guardian_confirmation_out_of_order'
    clock.value += timedelta(seconds=902)
    assert adapter.command('renew', 'one', str(uuid4()), adapter.owner_instance_id, 'x', NOW)[1]['code'] == 'guardian_confirmation_expired'
    assert adapter.store.path.read_bytes() == before
    clock.value = NOW
    assert renew(env).json()['code'] == 'guardian_clock_unavailable'


def test_commit_time_expiry_writes_nothing(env, monkeypatch):
    _, adapter, _, clock = env
    start(env)
    before = adapter.store.path.read_bytes()
    original = adapter.store.before_publish
    def delayed():
        clock.value += timedelta(seconds=901)
        original()
    monkeypatch.setattr(adapter.store, 'before_publish', delayed)
    r = renew(env)
    assert r.json()['code'] == 'guardian_confirmation_expired'
    assert adapter.store.path.read_bytes() == before
    assert adapter.lifecycle.owner_execution_id is None


@pytest.mark.parametrize('operation', ['start', 'renew', 'stop'])
def test_publication_failure_partial_commit_replay(env, monkeypatch, operation):
    api, adapter, svc, _ = env
    if operation != 'start': start(env)
    def fail(_): raise OSError('sensitive path')
    monkeypatch.setattr(adapter.store, 'write', fail)
    key = str(uuid4())
    if operation == 'renew':
        r = renew(env, key=key)
        again = renew(env, key=key)
    else:
        payload = transition('completed' if operation == 'stop' else 'in_progress')
        headers = {'Idempotency-Key': key, 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id}
        r = api.post('/v1/execution-transitions', json=payload, headers=headers)
        again = api.post('/v1/execution-transitions', json=payload, headers=headers)
    assert r.status_code == 503 and r.json()['code'] == 'guardian_attestation_publication_failed'
    assert r.json()['execution_commit'] == ('not_attempted' if operation == 'renew' else 'committed')
    assert r.json()['ownership'] == 'lost' and again.json() == r.json()
    assert 'sensitive' not in r.text


def test_capacity_and_concurrent_same_key(env, monkeypatch):
    _, adapter, _, clock = env
    start(env)
    calls = []
    original = adapter.store.write
    def counted(evidence):
        calls.append(evidence)
        original(evidence)
    monkeypatch.setattr(adapter.store, 'write', counted)
    key = str(uuid4())
    def execute(_):
        return adapter.command('renew', 'one', key, adapter.owner_instance_id, 'x', clock.value)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(execute, range(16)))
    assert all(r[0] == 200 for r in results) and len(calls) == 1
    adapter.capacity = len(adapter.journal)
    assert renew(env).json()['code'] == 'guardian_command_capacity_exhausted'
    assert len(calls) == 1


@pytest.mark.parametrize('first', ['renew', 'stop'])
def test_renew_stop_race_orders(env, first):
    _, adapter, _, clock = env
    start(env)
    entered, release = Event(), Event()
    original = adapter.store.before_publish
    def barrier():
        entered.set()
        assert release.wait(5)
        original()
    adapter.store.before_publish = barrier
    destination = Execution('one', 'mission', Status.COMPLETED, NOW, NOW + timedelta(seconds=60), timedelta(seconds=60))
    def execute(kind):
        return adapter.command(kind, 'one', str(uuid4()), adapter.owner_instance_id, kind, clock.value,
                               destination if kind == 'stop' else None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(execute, first)
        assert entered.wait(5)
        b = pool.submit(execute, 'stop' if first == 'renew' else 'renew')
        release.set()
        first_result, second_result = a.result(), b.result()
    assert first_result[0] == 200
    assert second_result[0] == (200 if first == 'renew' else 409)
    assert adapter.store.read(clock.value).state is State.INACTIVE


def test_stop_replay_and_renew_replay_after_stop(env, monkeypatch):
    api, adapter, svc, clock = env
    start(env)
    key = str(uuid4())
    success = renew(env, key=key).json()
    calls = []
    original = svc.transition_execution
    def counted(value):
        calls.append(value)
        return original(value)
    monkeypatch.setattr(svc, 'transition_execution', counted)
    headers = {'Idempotency-Key': str(uuid4()), 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id}
    for _ in range(2):
        assert api.post('/v1/execution-transitions', json=transition('completed'), headers=headers).status_code == 200
    assert len(calls) == 1
    payload = adapter.store.path.read_bytes()
    replay = renew(env, key=key).json()
    assert replay['replayed'] and replay['expires_at'] == success['expires_at']
    assert adapter.store.path.read_bytes() == payload
    assert renew(env).json()['code'] == 'guardian_session_not_owned'


def test_command_body_conflict(env):
    api, adapter, _, _ = env
    key = start(env)
    headers = {'Idempotency-Key': key, 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id}
    r = api.post('/v1/execution-transitions', json=transition('completed'), headers=headers)
    assert r.json()['code'] == 'guardian_idempotency_conflict'
    assert adapter.lifecycle.owner_execution_id == 'one'


def test_unknown_state_revokes_and_no_write(env, monkeypatch):
    _, adapter, svc, _ = env
    start(env)
    payload = adapter.store.path.read_bytes()
    def fail(_): raise OSError('private')
    monkeypatch.setattr(svc, 'load_execution', fail)
    r = renew(env)
    assert r.status_code == 503 and r.json()['code'] == 'guardian_state_unavailable'
    assert adapter.lifecycle.owner_execution_id is None and adapter.store.path.read_bytes() == payload


@pytest.mark.parametrize('after_commit', [False, True])
def test_execution_persistence_uncertainty_does_not_publish(env, monkeypatch, after_commit):
    api, adapter, svc, _ = env
    original = svc.transition_execution
    def fail(value):
        if after_commit:
            original(value)
        raise OSError('private storage failure')
    monkeypatch.setattr(svc, 'transition_execution', fail)
    headers = {'Idempotency-Key': str(uuid4()), 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id}
    r = api.post('/v1/execution-transitions', json=transition(), headers=headers)
    assert r.status_code == 503 and r.json()['code'] == 'guardian_execution_persistence_failed'
    assert r.json()['execution_commit'] == 'unknown' and r.json()['guardian_publication'] == 'not_attempted'
    assert not adapter.store.path.exists()
    assert svc.load_execution('one').status is (Status.IN_PROGRESS if after_commit else Status.NOT_STARTED)
    assert api.post('/v1/execution-transitions', json=transition(), headers=headers).json() == r.json()


def test_double_filesystem_failure_original_expiry(env, monkeypatch):
    _, adapter, _, clock = env
    start(env)
    payload = adapter.store.path.read_bytes()
    def fail(_): raise OSError('write')
    def unlink_fail(*args, **kwargs): raise PermissionError('remove')
    monkeypatch.setattr(adapter.store, 'write', fail)
    monkeypatch.setattr(type(adapter.store.path), 'unlink', unlink_fail)
    assert renew(env).json()['code'] == 'guardian_attestation_publication_failed'
    assert adapter.store.path.read_bytes() == payload
    assert adapter.lifecycle.owner_execution_id is None
    clock.value += timedelta(seconds=901)
    assert adapter.store.read(clock.value) is None


def test_other_transition_journal_and_owned_bypass(env):
    api, adapter, svc, _ = env
    start(env)
    payload = dict(execution_id='one', mission_id='mission', status='unconfirmed',
                   actual_start=None, actual_end=None, actual_duration=None)
    headers = {'Idempotency-Key': str(uuid4()), 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id}
    assert api.post('/v1/execution-transitions', json=payload, headers=headers).status_code == 409
    assert svc.load_execution('one').status is Status.IN_PROGRESS
    payload['execution_id'] = 'two'
    adapter.lifecycle.revoke()
    headers['Idempotency-Key'] = str(uuid4())
    for _ in range(2):
        assert api.post('/v1/execution-transitions', json=payload, headers=headers).status_code == 200
    assert svc.load_execution('two').status is Status.UNCONFIRMED
    assert adapter.store.read(NOW).state is State.ACTIVE  # no attestation from UNCONFIRMED


def test_restart_can_explicitly_close_without_reclaim(env):
    _, adapter, svc, clock = env
    start(env)
    adapter.close()
    replacement = GuardianRenewalAdapter(svc, adapter.store.path, clock)
    try:
        destination = Execution('one', 'mission', Status.INTERRUPTED, NOW, NOW + timedelta(seconds=60), timedelta(seconds=60))
        assert replacement.command('stop', 'one', str(uuid4()), replacement.owner_instance_id, 'stop', NOW, destination)[0] == 200
        assert replacement.lifecycle.owner_execution_id is None
        assert replacement.store.read(NOW).state is State.INACTIVE
    finally:
        replacement.close()


def test_http_concurrent_key_and_semantic_timezone_replay(env):
    api, adapter, svc, _ = env
    key = start(env)
    payload = transition()
    payload['actual_start'] = NOW.astimezone(timezone(timedelta(hours=2))).isoformat()
    assert api.post('/v1/execution-transitions', json=payload, headers={
        'Idempotency-Key': key, 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id}).status_code == 200
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: renew(env, key=key), range(8)))
    assert all(r.status_code == 200 for r in results)
    assert sum(not r.json()['replayed'] for r in results) == 1


def test_execution_concurrency_rejection_no_publication(env, monkeypatch):
    from decision.execution_lineage_persistence import ExecutionLineageStaleStateError
    from decision.services.execution_outcome_application import ExecutionOutcomeApplicationError
    api, adapter, svc, _ = env
    def stale(_):
        try:
            raise ExecutionLineageStaleStateError('execution_stale_state')
        except ExecutionLineageStaleStateError as cause:
            raise ExecutionOutcomeApplicationError(str(cause)) from cause
    monkeypatch.setattr(svc, 'transition_execution', stale)
    r = api.post('/v1/execution-transitions', json=transition(), headers={
        'Idempotency-Key': str(uuid4()), 'X-Guardian-Owner-Instance-Id': adapter.owner_instance_id})
    assert r.status_code == 503 and r.json()['execution_commit'] == 'not_committed'
    assert r.json()['guardian_publication'] == 'not_attempted' and not adapter.store.path.exists()


@pytest.mark.parametrize('execution_id', ['bad id', '-bad', 'a' * 129])
def test_invalid_exact_path(env, execution_id):
    assert renew(env, execution_id=execution_id).status_code == 422
    assert env[0].get(f'/v1/executions/{execution_id}/guardian-renewal').status_code == 422


def test_clock_unavailable_and_response_loss_retry(env):
    _, adapter, _, clock = env
    start(env)
    key = str(uuid4())
    # Discard the response after commit, then recover its original result.
    adapter.command('renew', 'one', key, adapter.owner_instance_id, 'action', NOW)
    payload = adapter.store.path.read_bytes()
    clock.value += timedelta(seconds=10)
    replay = adapter.command('renew', 'one', key, adapter.owner_instance_id, 'action', clock.value)
    assert replay[1]['replayed'] and adapter.store.path.read_bytes() == payload
    clock.value = NOW.replace(tzinfo=None)
    assert renew(env).json()['code'] == 'guardian_clock_unavailable'


def test_writer_lock_excludes_other_process(env):
    import subprocess
    import sys
    adapter = env[1]
    script = '''
import sys
from astropilot.guardian_renewal_api import WriterLock
from pathlib import Path
lock = WriterLock(Path(sys.argv[1]))
try:
    lock.acquire()
except RuntimeError:
    sys.exit(0)
else:
    lock.close()
    sys.exit(1)
'''
    result = subprocess.run([sys.executable, '-c', script, str(adapter.store.path)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
