import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from astropilot.guardian_scheduler import GuardianScheduler, GuardianSchedulerCadence, GuardianSchedulerStatus as S
from decision.models.guardian_cycle import GuardianCycleResult, GuardianCycleStatus as C
from decision.models.guardian import GuardianObservation, GuardianAction
from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner
from decision.runners.guardian_runner import GuardianRunner

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)
STEP = timedelta(seconds=60)

def setup(runner=None):
    clock = Mock(return_value=NOW)
    if runner is None:
        runner = Mock()
        runner.run_cycle.side_effect = lambda *, logical_time: GuardianCycleResult(C.ASSESSED, logical_time, None)
    scheduler = GuardianScheduler(runner=runner, clock=clock,
        cadence=GuardianSchedulerCadence(interval=STEP, anchor=NOW))
    return scheduler, runner, clock

def test_first_repeat_next_and_rollback():
    scheduler, runner, clock = setup()
    result = scheduler.poll()
    assert result.status is S.COMPLETED and result.slot == NOW
    runner.run_cycle.assert_called_once_with(logical_time=NOW)
    assert scheduler.poll().reason == 'slot_already_reserved'
    clock.return_value = NOW + STEP
    assert scheduler.poll().status is S.COMPLETED
    clock.return_value = NOW
    assert scheduler.poll().status is S.SKIPPED
    assert runner.run_cycle.call_count == 2 and clock.call_count == 4
    with pytest.raises(FrozenInstanceError): result.reason = 'other'

def test_downtime_no_burst():
    scheduler, runner, clock = setup()
    scheduler.poll()
    clock.return_value = NOW + 100 * STEP + timedelta(seconds=12)
    assert scheduler.poll().slot == NOW + 100 * STEP
    assert runner.run_cycle.call_count == 2

def test_overlap_next_slot_is_not_reserved():
    entered, release = Event(), Event()
    runner = Mock()
    def cycle(*, logical_time):
        entered.set()
        assert release.wait(5)
        return GuardianCycleResult(C.ASSESSED, logical_time, None)
    runner.run_cycle.side_effect = cycle
    scheduler, _, clock = setup(runner)
    results = []
    thread = Thread(target=lambda: results.append(scheduler.poll()))
    thread.start()
    try:
        assert entered.wait(5)
        assert scheduler.poll().reason == 'cycle_in_progress'
        clock.return_value = NOW + STEP
        result = scheduler.poll()
        assert result.status is S.SKIPPED and result.reason == 'cycle_in_progress'
        assert runner.run_cycle.call_count == 1
    finally:
        release.set(); thread.join(5)
    assert not thread.is_alive() and results[0].status is S.COMPLETED
    assert scheduler.poll().status is S.COMPLETED
    assert runner.run_cycle.call_count == 2

@pytest.mark.parametrize('failure', [RuntimeError('secret'), None,
    GuardianCycleResult(C.ERROR, NOW, None), GuardianCycleResult(C.ASSESSED, NOW + STEP, None),
    GuardianCycleResult('bad', NOW, None)])
def test_error_consumes_slot_and_recovers(failure):
    scheduler, runner, clock = setup()
    runner.run_cycle.side_effect = None
    if isinstance(failure, Exception): runner.run_cycle.side_effect = failure
    else: runner.run_cycle.return_value = failure
    result = scheduler.poll()
    assert result.status is S.ERROR and result.reason == 'cycle_error'
    assert scheduler.poll().reason == 'slot_already_reserved'
    runner.run_cycle.side_effect = lambda *, logical_time: GuardianCycleResult(C.ASSESSED, logical_time, None)
    clock.return_value = NOW + STEP
    assert scheduler.poll().status is S.COMPLETED
    assert runner.run_cycle.call_count == 2

def test_process_control_releases_lock():
    scheduler, runner, clock = setup()
    runner.run_cycle.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): scheduler.poll()
    assert scheduler.poll().reason == 'slot_already_reserved'
    clock.return_value = NOW + STEP
    runner.run_cycle.side_effect = lambda *, logical_time: GuardianCycleResult(C.ASSESSED, logical_time, None)
    assert scheduler.poll().status is S.COMPLETED

def test_utc_jitter_and_before_anchor():
    scheduler, runner, clock = setup()
    clock.return_value = (NOW + timedelta(seconds=59)).astimezone(timezone(timedelta(hours=2)))
    assert scheduler.poll().slot.tzinfo is timezone.utc
    runner.run_cycle.assert_called_once_with(logical_time=NOW)
    clock.return_value = NOW - timedelta(microseconds=1)
    assert scheduler.poll().reason == 'before_anchor'

@pytest.mark.parametrize('value', [None, 'now', NOW.replace(tzinfo=None)])
def test_invalid_clock(value):
    scheduler, runner, clock = setup()
    clock.return_value = value
    with pytest.raises(ValueError): scheduler.poll()
    runner.run_cycle.assert_not_called()

@pytest.mark.parametrize('interval', [None, 60, timedelta(0), -STEP, timedelta(microseconds=1)])
def test_invalid_cadence(interval):
    with pytest.raises(ValueError): GuardianSchedulerCadence(interval=interval, anchor=NOW)

def test_anchor_and_boundary():
    cadence = GuardianSchedulerCadence(interval=STEP, anchor=NOW.astimezone(timezone(timedelta(hours=2))))
    assert cadence.anchor.tzinfo is timezone.utc
    assert cadence.slot(NOW + STEP - timedelta(microseconds=1)) == NOW
    assert cadence.slot(NOW + STEP) == NOW + STEP
    with pytest.raises(ValueError): GuardianSchedulerCadence(interval=STEP, anchor=NOW.replace(tzinfo=None))

def test_missing_evidence_stays_fail_closed():
    evidence, session = Mock(return_value=GuardianObservation()), Mock(return_value=None)
    runner = GuardianPeriodicRunner(evidence_provider=evidence, session_context_provider=session, guardian_runner=GuardianRunner())
    scheduler, _, _ = setup(runner)
    result = scheduler.poll()
    assert result.status is S.COMPLETED
    assert not result.cycle.decision_eligible
    assert result.cycle.recommended_action is GuardianAction.EMERGENCY_STOP
    evidence.assert_called_once_with(NOW); session.assert_called_once_with(NOW)

def test_dependency_boundary_and_no_hidden_io(monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'astropilot/guardian_scheduler.py'
    tree = ast.parse(path.read_text())
    allowed = {'contextlib', 'astropilot.guardian_scheduler_state', 'dataclasses', 'datetime', 'enum', 'threading', 'typing',
        'decision.models.guardian_cycle', 'decision.runners.guardian_periodic_runner'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): assert all(n.name in allowed for n in node.names)
        if isinstance(node, ast.ImportFrom): assert node.module in allowed
        if isinstance(node, ast.Call):
            assert not (isinstance(node.func, ast.Name) and node.func.id in {'open', '__import__', 'eval', 'exec'})
            assert not (isinstance(node.func, ast.Attribute) and node.func.attr in {'now', 'utcnow', 'sleep', 'evaluate'})
    assert not any(isinstance(n, (ast.While, ast.AsyncFunctionDef)) for n in ast.walk(tree))
    import socket, subprocess, builtins
    def forbidden(*args, **kwargs): raise AssertionError('Unexpected I/O')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(builtins, 'open', forbidden)
    assert setup()[0].poll().status is S.COMPLETED

def test_explicit_version_and_allowlisted_reasons():
    from astropilot.guardian_scheduler import GuardianSchedulerResult
    with pytest.raises(ValueError):
        GuardianSchedulerCadence(interval=STEP, anchor=NOW, version='unknown')
    with pytest.raises(ValueError):
        GuardianSchedulerResult(S.ERROR, NOW, 'secret')
    with pytest.raises(ValueError):
        GuardianSchedulerResult(S.COMPLETED, NOW, 'cycle_error')
    assert setup()[0].poll().version == 'guardian-scheduler-v1'

def test_restart_boundary_is_explicitly_in_memory():
    first, runner, clock = setup()
    first.poll()
    recreated = GuardianScheduler(runner=runner, clock=clock,
        cadence=GuardianSchedulerCadence(interval=STEP, anchor=NOW))
    assert recreated.poll().status is S.COMPLETED
    assert runner.run_cycle.call_count == 2

def test_runner_error_preserves_fail_closed_cycle():
    runner = GuardianPeriodicRunner(evidence_provider=Mock(side_effect=RuntimeError()),
        session_context_provider=Mock(return_value=None), guardian_runner=GuardianRunner())
    result = setup(runner)[0].poll()
    assert result.status is S.ERROR
    assert result.cycle.status is C.ERROR
    assert not result.cycle.decision_eligible
    assert result.cycle.recommended_action is GuardianAction.EMERGENCY_STOP
