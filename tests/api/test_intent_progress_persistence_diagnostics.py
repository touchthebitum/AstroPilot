"""Real atomic profile writes, failures and restart/replay; no real user data."""
import errno
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from astropilot.persistence_diagnostics import HEADER
from test_execution_session_api import setup, create_completed, credit


@pytest.fixture
def support_log(tmp_path):
    parent = logging.getLogger('astropilot.launcher')
    level = parent.level
    path = tmp_path / 'support.log'
    handler = logging.FileHandler(path, encoding='utf-8')
    parent.addHandler(handler)
    parent.setLevel(logging.INFO)
    try:
        yield path
    finally:
        parent.removeHandler(handler)
        parent.setLevel(level)
        handler.close()


def events(path):
    records = [json.loads(line.split('persistence_diagnostic ', 1)[1])
               for line in path.read_text(encoding='utf-8').splitlines()
               if 'persistence_diagnostic ' in line]
    for row in records:
        assert set(row) == {'schema_version','event','diagnostic_id','occurred_at_utc',
                           'operation','category','duration_ms','http_status'}
        assert row['operation'] == 'intent_progress_credit'
        assert re.fullmatch('[a-f0-9]{32}', row['diagnostic_id'])
        assert row['duration_ms'] >= 0
        assert datetime.fromisoformat(row['occurred_at_utc']).utcoffset() == timedelta(0)
    return records


@pytest.mark.parametrize('number,category', [
    (errno.EACCES,'permission_denied'), (errno.ENOSPC,'storage_full'),
    (errno.EROFS,'read_only_storage'), (getattr(errno,'EDQUOT',-1),'quota_exceeded'),
    (errno.EIO,'io_error'),
])
def test_failed_atomic_write_is_sanitized_correlated_and_recovers(tmp_path, monkeypatch, support_log, number, category):
    fresh = setup(tmp_path / 'data', monkeypatch)
    api = fresh()
    create_completed(api, 'execution-1', evidence_id='evidence-1')
    profile = tmp_path / 'data' / 'user_profile.json'
    before = profile.read_bytes()
    original = Path.replace
    calls = []
    def fail(path, target):
        if Path(target) == profile:
            calls.append(target)
            raise OSError(number, 'SECRET token https://private.invalid /Users/private/profile.json')
        return original(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'replace', fail)
        failed = credit(api, 'execution-1', 'evidence-1', confirm=True)
    assert failed.status_code == 503
    assert failed.json()['detail']['code'] == 'intent_progress_persistence_unavailable'
    assert failed.json()['detail']['category'] == category
    assert len(calls) == 1
    assert profile.read_bytes() == before
    assert not list(profile.parent.glob('.user_profile.*.tmp'))
    assert fresh().get('/v1/executions/execution-1/session').json()['credit'] is None
    logged = events(support_log)
    assert len(logged) == 1
    assert logged[0]['diagnostic_id'] == failed.headers[HEADER]
    assert logged[0]['category'] == category
    assert logged[0]['http_status'] == 503
    assert logged[0]['event'] == 'intent_progress_persistence_failed'
    recovered = credit(fresh(), 'execution-1', 'evidence-1', confirm=True)
    assert recovered.status_code == 200 and recovered.json()['status'] == 'applied'
    saved = profile.read_bytes()
    replayed = credit(fresh(), 'execution-1', 'evidence-1')
    assert replayed.status_code == 200 and replayed.json()['status'] == 'already_applied'
    assert profile.read_bytes() == saved
    state = fresh().get('/v1/executions/execution-1/session').json()
    assert state['acquired_after_seconds'] == 5400
    assert len(json.loads(saved)['intent_progress_credits']) == 1
    logged = events(support_log)
    assert [r['diagnostic_id'] for r in logged] == [r.headers[HEADER] for r in (failed,recovered,replayed)]
    assert len({r['diagnostic_id'] for r in logged}) == 3
    for secret in ('SECRET','private.invalid','/Users/private','token'):
        assert secret not in support_log.read_text() and secret not in failed.text


def test_error_after_replace_requires_readback_and_replay_without_second_credit(tmp_path, monkeypatch, support_log):
    fresh = setup(tmp_path / 'data', monkeypatch)
    create_completed(fresh(), 'execution-1', evidence_id='evidence-1')
    profile = tmp_path / 'data' / 'user_profile.json'
    original = Path.replace
    def committed_but_error(path, target):
        result = original(path, target)
        if Path(target) == profile:
            raise OSError(errno.EIO, 'SECRET acknowledgement lost after replacement')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path,'replace',committed_but_error)
        failed = credit(fresh(),'execution-1','evidence-1',confirm=True)
    assert failed.status_code == 503
    assert 'not be confirmed' in failed.json()['detail']['message']
    canonical = fresh().get('/v1/executions/execution-1/session').json()
    assert canonical['credit'] is not None and canonical['acquired_after_seconds'] == 5400
    before = profile.read_bytes()
    replay = credit(fresh(),'execution-1','evidence-1')
    assert replay.json()['status'] == 'already_applied'
    assert profile.read_bytes() == before
    assert len(events(support_log)) == 2


def test_concurrent_failure_ids_are_request_local(tmp_path, monkeypatch, support_log):
    fresh = setup(tmp_path / 'data', monkeypatch)
    create_completed(fresh(), 'execution-1', evidence_id='evidence-1')
    original = Path.replace
    profile = tmp_path / 'data' / 'user_profile.json'
    def fail(path, target):
        if Path(target) == profile: raise PermissionError(errno.EACCES,'SECRET')
        return original(path,target)
    monkeypatch.setattr(Path,'replace',fail)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: credit(fresh(),'execution-1','evidence-1',confirm=True), range(2)))
    assert [r.status_code for r in replies] == [503,503]
    assert len({r.headers[HEADER] for r in replies}) == 2
    assert {r['diagnostic_id'] for r in events(support_log)} == {r.headers[HEADER] for r in replies}


@pytest.mark.parametrize('write_fails', [False, True])
def test_diagnostic_sink_failure_cannot_replace_result(tmp_path, monkeypatch, write_fails):
    from astropilot import persistence_diagnostics
    fresh = setup(tmp_path / 'data', monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    def broken(*args, **kwargs): raise OSError('log disk failure')
    monkeypatch.setattr(persistence_diagnostics._LOGGER, 'info', broken)
    if write_fails:
        original = Path.replace
        def fail(path, target):
            if Path(target).name == 'user_profile.json': raise OSError(errno.ENOSPC,'SECRET')
            return original(path,target)
        monkeypatch.setattr(Path,'replace',fail)
    result = credit(fresh(),'execution-1','evidence-1',confirm=True)
    state = fresh().get('/v1/executions/execution-1/session').json()
    if write_fails:
        assert result.status_code == 503
        assert result.json()['detail']['category'] == 'storage_full'
        assert state['credit'] is None
    else:
        assert result.status_code == 200 and result.json()['status'] == 'applied'
        assert state['acquired_after_seconds'] == 5400


def test_programming_error_is_not_reported_as_storage_failure(tmp_path, monkeypatch):
    fresh = setup(tmp_path / 'data', monkeypatch)
    create_completed(fresh(),'execution-1',evidence_id='evidence-1')
    original = Path.replace
    def fail(path,target):
        if Path(target).name == 'user_profile.json': raise RuntimeError('programming error')
        return original(path,target)
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(RuntimeError,match='programming error'):
        credit(fresh(),'execution-1','evidence-1',confirm=True)
