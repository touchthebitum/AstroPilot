import json
import multiprocessing
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from astropilot.guardian_scheduler import GuardianScheduler, GuardianSchedulerCadence
from astropilot.guardian_scheduler_state import GuardianSchedulerStateStore
from decision.models.guardian_cycle import GuardianCycleResult, GuardianCycleStatus

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)
CADENCE = GuardianSchedulerCadence(interval=timedelta(seconds=60), anchor=NOW)

def make(directory, now=NOW):
    runner = Mock()
    runner.run_cycle.side_effect = lambda *, logical_time: GuardianCycleResult(GuardianCycleStatus.ASSESSED, logical_time, None)
    store = GuardianSchedulerStateStore(directory)
    return GuardianScheduler(runner=runner, clock=lambda: now, cadence=CADENCE, state_store=store), runner, store

def test_restart_next_and_dedicated_unicode_path(tmp_path):
    directory = tmp_path / 'État avec espaces'
    scheduler, runner, store = make(directory)
    assert scheduler.poll().reason == 'cycle_completed'
    doc = json.loads(store.path.read_text())
    assert doc['schema_version'] == 1
    assert doc['last_completed_slot'] == doc['last_reserved_slot'] == NOW.isoformat()
    restarted, runner2, _ = make(directory)
    assert restarted.poll().reason == 'slot_already_reserved'
    runner2.run_cycle.assert_not_called()
    future, runner3, _ = make(directory, NOW + timedelta(seconds=600))
    assert future.poll().reason == 'cycle_completed'
    runner3.run_cycle.assert_called_once()
    assert {p.name for p in directory.iterdir()} == {'guardian_scheduler'}
    assert {p.name for p in store.directory.iterdir()} == {'state.json', '.lock'}

@pytest.mark.parametrize('payload', ['{', '{"schema_version":2}', '{}', '{"schema_version":1,"schema_version":1}', '[' * 2000 + ']' * 2000])
def test_corrupt_fail_closed(tmp_path, payload):
    scheduler, runner, store = make(tmp_path)
    store.directory.mkdir()
    store.path.write_text(payload)
    assert scheduler.poll().reason == 'state_error'
    runner.run_cycle.assert_not_called()
    assert store.path.read_text() == payload

def test_crash_after_claim(tmp_path):
    scheduler, runner, store = make(tmp_path)
    runner.run_cycle.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt): scheduler.poll()
    assert json.loads(store.path.read_text())['last_completed_slot'] is None
    restarted, runner2, _ = make(tmp_path)
    assert restarted.poll().reason == 'slot_already_reserved'
    runner2.run_cycle.assert_not_called()
    assert make(tmp_path, NOW + timedelta(seconds=60))[0].poll().reason == 'cycle_completed'

def test_partial_write(tmp_path, monkeypatch):
    scheduler, _, store = make(tmp_path)
    assert scheduler.poll().reason == 'cycle_completed'
    original = store.path.read_bytes()
    import astropilot.guardian_scheduler_state as module
    monkeypatch.setattr(module.os, 'replace', Mock(side_effect=OSError))
    future, runner, _ = make(tmp_path, NOW + timedelta(seconds=60))
    assert future.poll().reason == 'state_error'
    runner.run_cycle.assert_not_called()
    assert store.path.read_bytes() == original
    assert not list(store.directory.glob('*.tmp'))

def worker(directory, ready, release, queue):
    scheduler, runner, _ = make(directory)
    def cycle(*, logical_time):
        ready.set()
        assert release.wait(10)
        return GuardianCycleResult(GuardianCycleStatus.ASSESSED, logical_time, None)
    runner.run_cycle.side_effect = cycle
    queue.put(scheduler.poll().reason)

def test_process_lock_overlap_and_restart(tmp_path):
    ctx = multiprocessing.get_context('spawn')
    ready, release, queue = ctx.Event(), ctx.Event(), ctx.Queue()
    process = ctx.Process(target=worker, args=(tmp_path, ready, release, queue))
    process.start()
    try:
        assert ready.wait(10)
        for now in (NOW, NOW + timedelta(seconds=60)):
            contender, runner, _ = make(tmp_path, now)
            assert contender.poll().reason == 'state_locked'
            runner.run_cycle.assert_not_called()
    finally:
        release.set()
        process.join(10)
        if process.is_alive(): process.terminate(); process.join()
    assert process.exitcode == 0
    assert queue.get(timeout=2) == 'cycle_completed'
    assert make(tmp_path)[0].poll().reason == 'slot_already_reserved'

@pytest.mark.parametrize('failure', [RuntimeError(), None])
def test_cycle_error_consumed_future_works(tmp_path, failure):
    scheduler, runner, _ = make(tmp_path)
    runner.run_cycle.side_effect = failure
    runner.run_cycle.return_value = None
    assert scheduler.poll().reason == 'cycle_error'
    assert make(tmp_path)[0].poll().reason == 'slot_already_reserved'
    assert make(tmp_path, NOW + timedelta(seconds=60))[0].poll().reason == 'cycle_completed'

def test_cadence_mismatch(tmp_path):
    scheduler, _, _ = make(tmp_path)
    scheduler.poll()
    other, runner, _ = make(tmp_path)
    other._cadence = GuardianSchedulerCadence(interval=timedelta(seconds=30), anchor=NOW)
    assert other.poll().reason == 'state_error'
    runner.run_cycle.assert_not_called()

def test_real_process_death_consumes_claim(tmp_path):
    ctx = multiprocessing.get_context('spawn')
    ready, release, queue = ctx.Event(), ctx.Event(), ctx.Queue()
    process = ctx.Process(target=worker, args=(tmp_path, ready, release, queue))
    process.start()
    try:
        assert ready.wait(10)
    finally:
        process.terminate()
        process.join(10)
    scheduler, runner, store = make(tmp_path)
    assert scheduler.poll().reason == 'slot_already_reserved'
    runner.run_cycle.assert_not_called()
    assert json.loads(store.path.read_text())['last_completed_slot'] is None
    assert make(tmp_path, NOW + timedelta(seconds=60))[0].poll().reason == 'cycle_completed'

def test_threads_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    schedulers = [make(tmp_path) for _ in range(2)]
    def poll(item):
        barrier.wait(timeout=5)
        return item[0].poll().reason
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(poll, schedulers))
    assert results.count('cycle_completed') == 1
    assert sum(item[1].run_cycle.call_count for item in schedulers) == 1

@pytest.mark.parametrize('key,value', [
    ('last_reserved_slot', '2026-10-09T00:00:01+00:00'),
    ('last_reserved_slot', '2026-10-09T00:00:00'),
    ('last_completed_slot', '2026-10-09T00:01:00+00:00'),
    ('schema_version', True), ('schema_version', 2), ('extra', None),
])
def test_invalid_watermarks(tmp_path, key, value):
    scheduler, _, store = make(tmp_path)
    scheduler.poll()
    doc = json.loads(store.path.read_text())
    doc[key] = value
    store.path.write_text(json.dumps(doc))
    future, runner, _ = make(tmp_path, NOW + timedelta(seconds=60))
    assert future.poll().reason == 'state_error'
    runner.run_cycle.assert_not_called()

def test_completion_failure_keeps_claim(tmp_path, monkeypatch):
    scheduler, runner, store = make(tmp_path)
    original = store._write
    calls = []
    def write(doc):
        calls.append(doc.copy())
        if len(calls) == 2:
            from astropilot.guardian_scheduler_state import GuardianSchedulerStateError
            raise GuardianSchedulerStateError()
        original(doc)
    monkeypatch.setattr(store, '_write', write)
    assert scheduler.poll().reason == 'state_error'
    runner.run_cycle.assert_called_once()
    assert make(tmp_path)[0].poll().reason == 'slot_already_reserved'
    assert make(tmp_path, NOW + timedelta(seconds=60))[0].poll().reason == 'cycle_completed'

def test_file_fsync_failure_no_evaluation(tmp_path, monkeypatch):
    import astropilot.guardian_scheduler_state as module
    scheduler, runner, store = make(tmp_path)
    monkeypatch.setattr(module.os, 'fsync', Mock(side_effect=OSError))
    assert scheduler.poll().reason == 'state_error'
    runner.run_cycle.assert_not_called()
    assert not store.path.exists()
    assert not list(store.directory.glob('*.tmp'))

def test_store_requires_lock(tmp_path):
    from astropilot.guardian_scheduler_state import GuardianSchedulerStateError
    _, _, store = make(tmp_path)
    with pytest.raises(GuardianSchedulerStateError): store.claim(NOW, CADENCE)
    with pytest.raises(GuardianSchedulerStateError): store.complete(NOW, CADENCE)

def test_store_dependency_boundary():
    import ast
    import sys
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parents[2] / 'astropilot/guardian_scheduler_state.py').read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): names = [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom): names = [node.module]
        else: continue
        assert all(name in sys.stdlib_module_names for name in names)

def test_windows_nonblocking_backend(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import astropilot.guardian_scheduler_state as module
    _, _, store = make(tmp_path)
    calls = []
    fake = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0,
                           locking=lambda fd, mode, count: calls.append((mode, count)))
    monkeypatch.setitem(sys.modules, 'msvcrt', fake)
    monkeypatch.setattr(module, 'os', SimpleNamespace(name='nt'))
    with store.locked(): pass
    assert calls == [(2, 1), (0, 1)]
    fake.locking = Mock(side_effect=BlockingIOError(11, 'busy'))
    from astropilot.guardian_scheduler_state import GuardianSchedulerStateLocked
    with pytest.raises(GuardianSchedulerStateLocked):
        with store.locked(): pytest.fail('contention entered lock')

@pytest.mark.skipif(__import__('os').name == 'nt', reason='POSIX directory fsync')
def test_directory_fsync_failure_retains_claim(tmp_path, monkeypatch):
    import astropilot.guardian_scheduler_state as module
    scheduler, runner, store = make(tmp_path)
    original = module.os.fsync
    calls = []
    def sync(fd):
        calls.append(fd)
        if len(calls) == 2: raise OSError('directory sync failure')
        original(fd)
    monkeypatch.setattr(module.os, 'fsync', sync)
    assert scheduler.poll().reason == 'state_error'
    runner.run_cycle.assert_not_called()
    assert json.loads(store.path.read_text())['last_reserved_slot'] == NOW.isoformat()
    assert make(tmp_path)[0].poll().reason == 'slot_already_reserved'


def test_corruption_after_same_instance_completion(tmp_path):
    scheduler, runner, store = make(tmp_path)
    scheduler.poll()
    store.path.write_text('{')
    assert scheduler.poll().reason == 'state_error'
    assert runner.run_cycle.call_count == 1
