"""Characterize existing lifecycle prerequisites, not a production HTTP adapter."""
from datetime import datetime, timedelta, timezone

import pytest

from astropilot.guardian_session_lifecycle import GuardianSessionLifecycle
from decision.models.execution import Execution, ExecutionStatus as Status
from decision.models.guardian import GuardianSessionState as State
from decision.models.guardian_live_session import GuardianLiveSessionEvidence
from astropilot.guardian_session_store import GuardianSessionStore
from decision.services.execution_outcome_application import ExecutionOutcomeApplicationService

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


def setup(tmp_path):
    service = ExecutionOutcomeApplicationService(mission_loader=lambda _: None)
    service.lineage_store.create_execution(
        Execution('session', 'mission', Status.NOT_STARTED, None, None, None))
    store = GuardianSessionStore(tmp_path / 'session.json')
    return service, store, GuardianSessionLifecycle(service, store)


def started():
    return Execution('session', 'mission', Status.IN_PROGRESS, NOW, None, None)


def stopped():
    end = NOW + timedelta(seconds=60)
    return Execution('session', 'mission', Status.COMPLETED, NOW, end, end - NOW)


def test_wrong_id_cannot_mutate_or_revoke_correct_owner(tmp_path):
    _, store, caller = setup(tmp_path)
    caller.start(started(), observed_at=NOW)
    original = store.path.read_bytes()
    with pytest.raises(ValueError, match='not_owned'):
        caller.renew('wrong-execution', observed_at=NOW + timedelta(seconds=10))
    assert store.path.read_bytes() == original
    assert caller.renew('session', observed_at=NOW + timedelta(seconds=20)).session_id == 'session'


@pytest.mark.parametrize('damage', ['corrupt', 'mismatch', 'inactive', 'future'])
def test_untrustworthy_attestation_revokes_and_cannot_be_repaired_into_ownership(tmp_path, damage):
    _, store, caller = setup(tmp_path)
    valid = caller.start(started(), observed_at=NOW)
    if damage == 'corrupt':
        store.path.write_text('{broken')
    else:
        store.write(GuardianLiveSessionEvidence(
            State.INACTIVE if damage == 'inactive' else State.ACTIVE,
            NOW + timedelta(seconds=60) if damage == 'future' else NOW,
            valid.source, valid.provenance,
            'other' if damage == 'mismatch' else 'session'))
    original = store.path.read_bytes()
    with pytest.raises(ValueError, match='attestation_lost'):
        caller.renew('session', observed_at=NOW)
    assert store.path.read_bytes() == original
    store.write(valid)
    with pytest.raises(ValueError, match='not_owned'):
        caller.renew('session', observed_at=NOW)


def test_external_execution_closure_prevents_renewal(tmp_path):
    service, store, caller = setup(tmp_path)
    caller.start(started(), observed_at=NOW)
    original = store.path.read_bytes()
    service.transition_execution(stopped())
    with pytest.raises(ValueError, match='attestation_lost'):
        caller.renew('session', observed_at=NOW + timedelta(seconds=60))
    assert service.load_execution('session').status is Status.COMPLETED
    assert store.path.read_bytes() == original
    with pytest.raises(ValueError, match='not_owned'):
        caller.renew('session', observed_at=NOW + timedelta(seconds=61))


def test_reads_and_construction_never_refresh_or_restore_ownership(tmp_path):
    service, store, caller = setup(tmp_path)
    caller.start(started(), observed_at=NOW)
    original = store.path.read_bytes()
    restarted = GuardianSessionLifecycle(service, store)
    for seconds in (0, 899, 900, 901):
        time = NOW + timedelta(seconds=seconds)
        service.load_execution('session')
        evidence = store.read(time)
        assert (evidence is not None) == (seconds <= 900)
        assert store.path.read_bytes() == original
    with pytest.raises(ValueError, match='not_owned'):
        restarted.renew('session', observed_at=NOW)
