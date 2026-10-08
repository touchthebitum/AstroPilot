"""Durable claims are suppression state, never replay authority."""
import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from datetime import timedelta
from dataclasses import replace

import pytest
from test_opportunity_alerts_v1 import complete, policy, decide
from test_modern_mission_authorization import START, assembly_environment
from astropilot.opportunity_alert_ledger import FileOpportunityAlertLedger, OpportunityAlertLedgerError


def claim(directory, key='a', family='f', at=START, **kwargs):
    return FileOpportunityAlertLedger(directory).claim(key=key, family=family,
        logical_time=at, cooldown_minutes=60, **kwargs)


def worker(directory):
    return claim(directory)


def test_restart_service_suppresses(complete, policy, tmp_path):
    assert decide(complete, policy, FileOpportunityAlertLedger(tmp_path)).alert
    assert decide(complete, policy, FileOpportunityAlertLedger(tmp_path)).alert is None


def test_expiration_exact_keys_and_families(tmp_path):
    assert claim(tmp_path)
    assert not claim(tmp_path, key='b', at=START + timedelta(minutes=59))
    assert claim(tmp_path, key='c', family='other', at=START + timedelta(minutes=59))
    assert claim(tmp_path, key='b', at=START + timedelta(minutes=60))
    assert not claim(tmp_path, at=START + timedelta(days=2))
    assert not claim(tmp_path, key='new', family='new', at=START)


@pytest.mark.parametrize('processes', [False, True])
def test_concurrency(tmp_path, processes):
    pool_type = ProcessPoolExecutor if processes else ThreadPoolExecutor
    options = {'mp_context': multiprocessing.get_context('spawn')} if processes else {}
    with pool_type(max_workers=4, **options) as pool:
        assert sum(pool.map(worker, [str(tmp_path)] * 16)) == 1


def test_absent_and_default_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    store = FileOpportunityAlertLedger()
    assert not store.path.exists()
    assert store.claim(key='a', family='f', logical_time=START, cooldown_minutes=60)
    assert store.path == tmp_path / 'opportunity_alert_ledger.json'
    doc = json.loads(store.path.read_text())
    assert doc['schema_version'] == 1
    assert doc['entries']['a']['policy_version'] == 1
    assert not (tmp_path / 'user_profile.json').exists()


@pytest.mark.parametrize('document', ['{', 'null', '{}', '{"schema_version":2}', '\\xff',
    '{"schema_version":1,"schema_version":1}'])
def test_corruption_never_emits(tmp_path, document, complete, policy):
    path = tmp_path / 'opportunity_alert_ledger.json'
    path.write_text(document)
    with pytest.raises(OpportunityAlertLedgerError, match='corrupt'):
        decide(complete, policy, FileOpportunityAlertLedger(tmp_path))
    assert path.read_text() == document


def test_partial_write_preserves_canonical(tmp_path, monkeypatch):
    import astropilot.opportunity_alert_ledger as module
    assert claim(tmp_path)
    path = tmp_path / 'opportunity_alert_ledger.json'
    before = path.read_bytes()
    def interrupted(*args):
        raise OSError('interrupted replace')
    with monkeypatch.context() as patch:
        patch.setattr(module.os, 'replace', interrupted)
        with pytest.raises(OpportunityAlertLedgerError, match='unavailable'):
            claim(tmp_path, key='b', family='new')
    assert path.read_bytes() == before
    assert not claim(tmp_path)
    assert claim(tmp_path, key='b', family='new')


def test_policy_change_never_resets_claims(tmp_path):
    assert claim(tmp_path)
    with pytest.raises(OpportunityAlertLedgerError, match='policy'):
        claim(tmp_path, key='b', policy_version=2)
    assert not claim(tmp_path)
    path = tmp_path / 'opportunity_alert_ledger.json'
    doc = json.loads(path.read_text())
    doc['entries']['a']['policy_version'] = 2
    path.write_text(json.dumps(doc))
    with pytest.raises(OpportunityAlertLedgerError, match='corrupt'):
        claim(tmp_path, key='new')


def test_legacy_does_not_initialize_ledger(tmp_path, complete, policy):
    assert decide(replace(complete, alert_live_marker=None), policy,
        FileOpportunityAlertLedger(tmp_path)).alert is None
    assert not (tmp_path / 'opportunity_alert_ledger.json').exists()


@pytest.mark.parametrize('damage', ['timestamp', 'family', 'watermark', 'extra', 'version'])
def test_structural_corruption(tmp_path, damage):
    assert claim(tmp_path)
    path = tmp_path / 'opportunity_alert_ledger.json'
    doc = json.loads(path.read_text())
    if damage == 'timestamp': doc['entries']['a']['last_emitted'] = '2026-01-01'
    if damage == 'family': doc['families'] = {}
    if damage == 'watermark': doc['latest_logical_time'] = (START - timedelta(days=1)).isoformat()
    if damage == 'extra': doc['weather'] = {}
    if damage == 'version': doc['schema_version'] = True
    path.write_text(json.dumps(doc))
    with pytest.raises(OpportunityAlertLedgerError): claim(tmp_path, key='new')


def test_service_expiration_preserves_v1_contract(complete, policy, tmp_path, monkeypatch):
    import test_opportunity_alerts_v1 as v1
    # Replay the existing v1 scenario, reopening the store for every cycle.
    class RestartingLedger:
        def claim(self, **kwargs):
            return FileOpportunityAlertLedger(tmp_path).claim(**kwargs)
    monkeypatch.setattr(v1, 'InMemoryOpportunityAlertLedger', RestartingLedger)
    v1.test_exact_and_lineage_deduplication(complete, policy)


def test_interrupted_serialization_leaves_only_old_state(tmp_path, monkeypatch):
    import astropilot.opportunity_alert_ledger as module
    assert claim(tmp_path)
    before = (tmp_path / 'opportunity_alert_ledger.json').read_bytes()
    def partial(doc, stream, **kwargs):
        stream.write('{"schema_version":')
        stream.flush()
        raise OSError('interrupted write')
    with monkeypatch.context() as patch:
        patch.setattr(module.json, 'dump', partial)
        with pytest.raises(OpportunityAlertLedgerError):
            claim(tmp_path, key='b', family='other')
    assert (tmp_path / 'opportunity_alert_ledger.json').read_bytes() == before
    assert not list(tmp_path.glob('*.tmp'))
    # A process killed before cleanup may leave a temp file; it is never read.
    (tmp_path / '.opportunity_alert_ledger.orphan.tmp').write_text('{')
    assert not claim(tmp_path)
    assert claim(tmp_path, key='b', family='other')


def test_lock_failure_cannot_emit(tmp_path, complete, policy, monkeypatch):
    import astropilot.opportunity_alert_ledger as module
    def failed(*args):
        raise OSError('lock unavailable')
    monkeypatch.setattr(module, 'exclusive_file_lock', failed)
    with pytest.raises(OpportunityAlertLedgerError):
        decide(complete, policy, FileOpportunityAlertLedger(tmp_path))
    assert not (tmp_path / 'opportunity_alert_ledger.json').exists()


def test_forward_refusal_watermark_survives_restart(tmp_path):
    assert claim(tmp_path)
    assert not claim(tmp_path, at=START + timedelta(days=1))
    assert not claim(tmp_path, key='new', family='new', at=START + timedelta(hours=2))
