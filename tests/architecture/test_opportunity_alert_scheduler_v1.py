from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import Mock
import ast
import inspect

import pytest
from decision.runners.opportunity_alert_runner import OpportunityAlertCycleResult, OpportunityAlertCycleStatus as Cycle
from astropilot.opportunity_alert_scheduler import OpportunityAlertScheduler, SchedulerStatus, SchedulerCadence

START = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def setup(tmp_path, runner=None, **kwargs):
    runner = runner or Mock()
    runner.run_cycle.return_value = OpportunityAlertCycleResult(Cycle.NO_ALERT, False, START, ('alerts_disabled',))
    return OpportunityAlertScheduler(runner=runner, directory=tmp_path, clock=lambda: START, **kwargs), runner


def test_slots_restart_and_downtime(tmp_path):
    s, r = setup(tmp_path)
    assert s.poll(policy=None).status is SchedulerStatus.COMPLETED
    assert s.poll(policy=None).status is SchedulerStatus.SKIPPED
    restarted, _ = setup(tmp_path, r)
    assert restarted.poll(policy=None).status is SchedulerStatus.SKIPPED
    assert restarted.poll(policy=None, now=START + timedelta(hours=5, minutes=20)).slot == START + timedelta(hours=5)
    assert r.run_cycle.call_count == 2
    assert restarted.poll(policy=None, now=START).status is SchedulerStatus.SKIPPED


def test_overlap_shared_instances(tmp_path):
    entered, release = Event(), Event()
    s, r = setup(tmp_path)
    def long(**kwargs):
        entered.set()
        assert release.wait(5)
        return OpportunityAlertCycleResult(Cycle.NO_ALERT, False, kwargs['logical_time'], ())
    r.run_cycle.side_effect = long
    other, _ = setup(tmp_path, r)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(s.poll, policy=None)
        assert entered.wait(5)
        assert s.poll(policy=None, now=START + timedelta(hours=1)).status is SchedulerStatus.OVERLAP
        second = pool.submit(other.poll, policy=None)
        release.set()
        assert first.result().status is SchedulerStatus.COMPLETED
        assert second.result().status is SchedulerStatus.SKIPPED
    assert r.run_cycle.call_count == 1


def test_error_future_slot(tmp_path):
    s, r = setup(tmp_path)
    r.run_cycle.side_effect = RuntimeError('private')
    assert s.poll(policy=None).cycle.status is Cycle.ERROR
    r.run_cycle.side_effect = None
    assert s.poll(policy=None, now=START + timedelta(hours=1)).status is SchedulerStatus.COMPLETED
    assert r.run_cycle.call_count == 2


def test_utc_and_validation(tmp_path):
    s, r = setup(tmp_path)
    assert s.poll(policy=None, now=START.astimezone(timezone(timedelta(hours=2)))).slot == START
    assert r.run_cycle.call_args.kwargs['logical_time'] == START
    with pytest.raises(ValueError):
        s.poll(policy=None, now=START.replace(tzinfo=None))
    for interval in (timedelta(0), timedelta(microseconds=1), 12):
        with pytest.raises(ValueError):
            SchedulerCadence(interval=interval)


def test_boundary():
    import astropilot.opportunity_alert_scheduler as module
    imports = {n.module for n in ast.walk(ast.parse(inspect.getsource(module))) if isinstance(n, ast.ImportFrom)}
    assert imports <= {'contextlib', 'dataclasses', 'datetime', 'enum', 'pathlib', 'threading',
        'astropilot.file_lock', 'decision.runners.opportunity_alert_runner'}


def test_reserved_crash_skips_on_restart(tmp_path):
    s, r = setup(tmp_path)
    r.run_cycle.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        s.poll(policy=None)
    r.run_cycle.side_effect = None
    restarted, _ = setup(tmp_path, r)
    assert restarted.poll(policy=None).status is SchedulerStatus.SKIPPED
    assert restarted.poll(policy=None, now=START + timedelta(hours=1)).status is SchedulerStatus.COMPLETED
    assert r.run_cycle.call_count == 2


@pytest.mark.parametrize('damage', ['{broken', '{"schema_version":1,"schema_version":1}', '{}'])
def test_corruption_fail_closed(tmp_path, damage):
    s, r = setup(tmp_path)
    s.store.path.write_text(damage)
    assert s.poll(policy=None).status is SchedulerStatus.ERROR
    r.run_cycle.assert_not_called()
    assert s.store.path.read_text() == damage


def test_write_failures(tmp_path, monkeypatch):
    s, r = setup(tmp_path)
    original = s.store.write
    monkeypatch.setattr(s.store, 'write', Mock(side_effect=OSError()))
    assert s.poll(policy=None).status is SchedulerStatus.ERROR
    r.run_cycle.assert_not_called()
    calls = 0
    def fail_completion(doc):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError()
        original(doc)
    monkeypatch.setattr(s.store, 'write', fail_completion)
    assert s.poll(policy=None).status is SchedulerStatus.ERROR
    restarted, _ = setup(tmp_path, r)
    assert restarted.poll(policy=None).status is SchedulerStatus.SKIPPED
    assert r.run_cycle.call_count == 1


def test_cadence_mismatch_and_before_anchor(tmp_path):
    s, r = setup(tmp_path)
    assert s.poll(policy=None).status is SchedulerStatus.COMPLETED
    changed, _ = setup(tmp_path, r, cadence=SchedulerCadence(interval=timedelta(minutes=15)))
    assert changed.poll(policy=None).status is SchedulerStatus.ERROR
    assert r.run_cycle.call_count == 1
    assert s.poll(policy=None, now=datetime(1969, 1, 1, tzinfo=timezone.utc)).status is SchedulerStatus.SKIPPED


def test_real_disabled_runner(tmp_path):
    from decision.runners.opportunity_alert_runner import OpportunityAlertRunner
    from decision.models.opportunity_alert import OpportunityAlertPolicy
    service, ledger = Mock(), Mock()
    s = OpportunityAlertScheduler(runner=OpportunityAlertRunner(tonight_service=service, ledger=ledger),
        directory=tmp_path, clock=lambda: START)
    result = s.poll(policy=OpportunityAlertPolicy(), profile={}, weather=None)
    assert result.cycle.status is Cycle.NO_ALERT
    service.evaluate.assert_not_called()
    ledger.claim.assert_not_called()


def test_concurrent_next_slot_runs_after_completion(tmp_path):
    s, r = setup(tmp_path)
    entered, release = Event(), Event()
    active = 0
    def run(**kwargs):
        nonlocal active
        active += 1
        assert active == 1
        if kwargs['logical_time'] == START:
            entered.set()
            assert release.wait(5)
        active -= 1
        return OpportunityAlertCycleResult(Cycle.ERROR, False, kwargs['logical_time'], ('failure',))
    r.run_cycle.side_effect = run
    other, _ = setup(tmp_path, r)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(s.poll, policy=None)
        assert entered.wait(5)
        second = pool.submit(other.poll, policy=None, now=START + timedelta(hours=1))
        release.set()
        assert first.result().cycle.status is Cycle.ERROR
        assert second.result().cycle.status is Cycle.ERROR
    assert r.run_cycle.call_count == 2


def test_independent_processes_share_reservation(tmp_path):
    import subprocess
    import sys
    code = '''
import sys
from pathlib import Path
from datetime import datetime, timezone
from astropilot.opportunity_alert_scheduler import OpportunityAlertScheduler
from decision.runners.opportunity_alert_runner import OpportunityAlertCycleResult, OpportunityAlertCycleStatus
class Runner:
    def run_cycle(self, **kwargs):
        with (Path(sys.argv[1]) / 'calls').open('a') as handle:
            handle.write('called\\n')
        return OpportunityAlertCycleResult(OpportunityAlertCycleStatus.NO_ALERT, False, kwargs['logical_time'], ())
s = OpportunityAlertScheduler(runner=Runner(), directory=sys.argv[1], clock=lambda: datetime(2026,10,8,12,tzinfo=timezone.utc))
assert s.poll(policy=None).status.value in ('COMPLETED', 'SKIPPED')
'''
    processes = [subprocess.Popen([sys.executable, '-c', code, str(tmp_path)]) for _ in range(4)]
    try:
        assert all(p.wait(timeout=20) == 0 for p in processes)
    finally:
        for p in processes:
            if p.poll() is None:
                p.kill()
                p.wait()
    assert (tmp_path / 'calls').read_text() == 'called\n'


def test_explicit_live_cycle_time_preserves_slot_identity(tmp_path):
    s, r = setup(tmp_path)
    live = START + timedelta(minutes=45)
    result = s.poll(policy=None, now=live, cycle_time=live)
    assert result.slot == START
    assert r.run_cycle.call_args.kwargs['logical_time'] == live
    assert s.poll(policy=None, now=live, cycle_time=live).status is SchedulerStatus.SKIPPED
    for invalid in (START - timedelta(seconds=1), START + timedelta(hours=1), START.replace(tzinfo=None)):
        with pytest.raises(ValueError):
            s.poll(policy=None, now=live, cycle_time=invalid)
    assert r.run_cycle.call_count == 1
