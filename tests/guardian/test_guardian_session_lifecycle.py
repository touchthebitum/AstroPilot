from datetime import datetime, timedelta, timezone

import pytest

from astropilot.guardian_session_lifecycle import GuardianSessionLifecycle
from astropilot.guardian_session_store import GuardianSessionStore
from decision.models.execution import Execution, ExecutionStatus as Status
from decision.models.guardian import GuardianSessionState as State
from decision.services.execution_outcome_application import ExecutionOutcomeApplicationService

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


def setup(tmp_path):
    service = ExecutionOutcomeApplicationService(mission_loader=lambda _: None)
    service.lineage_store.create_execution(Execution('session', 'mission', Status.NOT_STARTED, None, None, None))
    store = GuardianSessionStore(tmp_path / 'session.json')
    return service, store, GuardianSessionLifecycle(service, store)


def started():
    return Execution('session', 'mission', Status.IN_PROGRESS, NOW, None, None)


def stopped():
    return Execution('session', 'mission', Status.COMPLETED, NOW, NOW + timedelta(seconds=60), timedelta(seconds=60))


def test_explicit_start_renew_stop(tmp_path):
    service, store, caller = setup(tmp_path)
    assert caller.start(started(), observed_at=NOW).state is State.ACTIVE
    stamp = NOW + timedelta(seconds=30)
    first = caller.renew('session', observed_at=stamp)
    assert caller.renew('session', observed_at=stamp) == first
    assert store(stamp).observed_at == stamp
    assert caller.stop(stopped(), observed_at=NOW + timedelta(seconds=60)).state is State.INACTIVE
    with pytest.raises(ValueError, match='not_owned'):
        caller.renew('session', observed_at=NOW + timedelta(seconds=61))


def test_crash_restart_and_expiration(tmp_path):
    service, store, caller = setup(tmp_path)
    caller.start(started(), observed_at=NOW)
    payload = store.path.read_bytes()
    restarted = GuardianSessionLifecycle(service, store)
    with pytest.raises(ValueError, match='not_owned'):
        restarted.renew('session', observed_at=NOW + timedelta(seconds=10))
    assert store.read(NOW + timedelta(seconds=900)) is not None
    assert store.read(NOW + timedelta(seconds=901)) is None
    assert store.path.read_bytes() == payload
    with pytest.raises(ValueError, match='attestation_lost'):
        caller.renew('session', observed_at=NOW + timedelta(seconds=901))
    assert store.read(NOW + timedelta(seconds=901)) is None


@pytest.mark.parametrize('operation', ['start', 'renew', 'stop'])
def test_write_errors_propagate_and_revoke(tmp_path, monkeypatch, operation):
    service, store, caller = setup(tmp_path)
    if operation != 'start':
        caller.start(started(), observed_at=NOW)
    def fail(*args):
        raise OSError('write failed')
    monkeypatch.setattr(store, 'write', fail)
    with pytest.raises(OSError, match='write failed'):
        if operation == 'start': caller.start(started(), observed_at=NOW)
        elif operation == 'stop': caller.stop(stopped(), observed_at=NOW)
        else: caller.renew('session', observed_at=NOW)
    assert store.read(NOW) is None
    with pytest.raises(ValueError, match='not_owned'):
        caller.renew('session', observed_at=NOW)


def test_invalid_transition_does_not_attest(tmp_path):
    service, store, caller = setup(tmp_path)
    with pytest.raises(ValueError): caller.stop(stopped(), observed_at=NOW)
    assert store.read(NOW) is None


def test_attestation_loss_never_resurrects(tmp_path):
    service, store, caller = setup(tmp_path)
    caller.start(started(), observed_at=NOW)
    store.path.unlink()
    with pytest.raises(ValueError, match='attestation_lost'):
        caller.renew('session', observed_at=NOW)
    assert store.read(NOW) is None


def test_duplicate_start_never_extends_and_restart_can_stop(tmp_path):
    service, store, caller = setup(tmp_path)
    caller.start(started(), observed_at=NOW)
    with pytest.raises(ValueError, match='already_owned'):
        caller.start(started(), observed_at=NOW + timedelta(seconds=10))
    assert store(NOW).observed_at == NOW
    restarted = GuardianSessionLifecycle(service, store)
    assert restarted.stop(stopped(), observed_at=NOW + timedelta(seconds=60)).state is State.INACTIVE
    with pytest.raises(ValueError):
        restarted.stop(stopped(), observed_at=NOW + timedelta(seconds=70))
    assert store(NOW + timedelta(seconds=70)).observed_at == NOW + timedelta(seconds=60)


def test_invalid_timestamp_does_not_commit_start(tmp_path):
    service, store, caller = setup(tmp_path)
    with pytest.raises(ValueError, match='timezone_required'):
        caller.start(started(), observed_at=NOW.replace(tzinfo=None))
    assert service.load_execution('session').status is Status.NOT_STARTED
    assert store.read(NOW) is None


def test_double_filesystem_failure_is_visible(tmp_path, monkeypatch):
    service, store, caller = setup(tmp_path)
    caller.start(started(), observed_at=NOW)
    def write_fail(*args): raise OSError('write failed')
    def remove_fail(*args, **kwargs): raise PermissionError('revocation failed')
    monkeypatch.setattr(store, 'write', write_fail)
    monkeypatch.setattr(type(store.path), 'unlink', remove_fail)
    with pytest.raises(PermissionError, match='revocation failed') as error:
        caller.stop(stopped(), observed_at=NOW)
    assert str(error.value.__context__) == 'write failed'
    with pytest.raises(ValueError, match='not_owned'):
        caller.renew('session', observed_at=NOW)
    assert store.read(NOW + timedelta(seconds=901)) is None
