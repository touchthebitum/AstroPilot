import ast
import json
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from astropilot.guardian_host import (
    GuardianHost, GuardianHostProviders, main, host_lock, HostAlreadyRunning,
    shutdown_signals, load_config,
)
from astropilot.guardian_scheduler import GuardianScheduler, GuardianSchedulerCadence
from astropilot.guardian_scheduler_state import GuardianSchedulerStateStore
from decision.models.guardian import GuardianObservation
from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner
from decision.runners.guardian_runner import GuardianRunner

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)
CADENCE = GuardianSchedulerCadence(interval=timedelta(seconds=60), anchor=NOW)


def config(tmp_path, **changes):
    doc = dict(schema_version=1, enabled=True, interval_seconds=60,
               anchor=NOW.isoformat(), provider='test')
    doc.update(changes)
    path = tmp_path / 'configuration é space.json'
    path.write_text(json.dumps(doc))
    return path


def invoke(tmp_path, capsys, *, clock=lambda: NOW, providers=None, **changes):
    path = config(tmp_path, **changes)
    providers = providers or GuardianHostProviders(lambda t: GuardianObservation(), lambda t: None)
    code = main(['--config', str(path), '--data-dir', str(tmp_path / 'État space'), '--once'],
                provider_factories={'test': lambda: providers}, clock=clock)
    return code, [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_start_restart_next_unknown(tmp_path, capsys):
    evidence = Mock(return_value=GuardianObservation())
    providers = GuardianHostProviders(evidence, lambda t: None)
    code, events = invoke(tmp_path, capsys, providers=providers)
    assert code == 0
    assert [e['event'] for e in events] == ['startup', 'cycle', 'shutdown']
    cycle = events[1]
    assert cycle['risk'] == 'UNKNOWN'
    assert cycle['action'] == 'EMERGENCY_STOP'
    assert cycle['session_applicability'] == 'UNKNOWN'
    assert cycle['decision_eligible'] is False
    evidence.assert_called_once_with(NOW)
    assert invoke(tmp_path, capsys, providers=providers)[1][1]['reason'] == 'slot_already_reserved'
    assert evidence.call_count == 1
    assert invoke(tmp_path, capsys, providers=providers, clock=lambda: NOW + timedelta(seconds=60))[0] == 0
    assert evidence.call_count == 2


def test_provider_error_consumed(tmp_path, capsys):
    providers = GuardianHostProviders(Mock(side_effect=RuntimeError('secret')), lambda t: None)
    code, events = invoke(tmp_path, capsys, providers=providers)
    assert code == 6
    assert events[1]['status'] == 'ERROR'
    assert events[1]['action'] == 'EMERGENCY_STOP'
    assert events[1]['decision_eligible'] is False
    assert events[1]['errors'] == ['evidence_provider_error']
    assert 'secret' not in json.dumps(events)
    assert events[-1] == {'event': 'shutdown'}
    assert invoke(tmp_path, capsys, providers=providers)[0] == 0
    assert providers.evidence.call_count == 1


def test_corrupt_state(tmp_path, capsys):
    path = tmp_path / 'État space' / 'guardian_scheduler' / 'state.json'
    path.parent.mkdir(parents=True)
    path.write_text('{')
    evidence = Mock(return_value=GuardianObservation())
    code, events = invoke(tmp_path, capsys, providers=GuardianHostProviders(evidence, lambda t: None))
    assert code == 5
    assert events[-2] == {'event': 'error', 'reason': 'state_error'}
    evidence.assert_not_called()
    assert path.read_text() == '{'


@pytest.mark.parametrize('changes', [dict(extra=1), dict(schema_version=True), dict(schema_version=2),
    dict(interval_seconds=True), dict(interval_seconds='60'), dict(interval_seconds=1.5),
    dict(interval_seconds=0), dict(enabled=1), dict(anchor=NOW.replace(tzinfo=None).isoformat()),
    dict(provider=None), dict(provider='module:factory')])
def test_invalid_config(tmp_path, changes):
    with pytest.raises(ValueError): load_config(config(tmp_path, **changes))


@pytest.mark.parametrize('payload', ['{', '[]', '{"schema_version":1,"schema_version":1}',
                                      '{"interval_seconds":NaN}'])
def test_malformed_config(tmp_path, payload):
    path = tmp_path / 'config.json'
    path.write_text(payload)
    with pytest.raises(ValueError): load_config(path)


def test_disabled_and_factory_fatal(tmp_path, capsys):
    assert invoke(tmp_path, capsys, enabled=False, provider=None)[0] == 0
    path = config(tmp_path)
    for factories in ({}, {'test': lambda: None}, {'test': Mock(side_effect=RuntimeError('secret'))}):
        assert main(['--config', str(path), '--data-dir', str(tmp_path)], provider_factories=factories) == 3
        assert 'secret' not in capsys.readouterr().out
    assert main(['--config', str(tmp_path / 'missing'), '--data-dir', str(tmp_path)]) == 2


def test_duplicate_host(tmp_path, capsys):
    path = config(tmp_path)
    with host_lock(tmp_path / '.guardian_host.lock'):
        with pytest.raises(HostAlreadyRunning):
            with host_lock(tmp_path / '.guardian_host.lock'): pass
        factory = Mock()
        assert main(['--config', str(path), '--data-dir', str(tmp_path)],
                    provider_factories={'test': factory}) == 4
        factory.assert_not_called()
    with host_lock(tmp_path / '.guardian_host.lock'): pass


@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_signals_restore(signum):
    stop = Event()
    old = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    with shutdown_signals(stop):
        signal.raise_signal(signum)
        assert stop.is_set()
    assert all(signal.getsignal(s) == old[s] for s in old)


def test_loop_one_poll_per_slot_overrun_and_interrupt(tmp_path):
    stop = Event()
    current = [NOW]
    evidence = Mock(return_value=GuardianObservation())
    runner = GuardianPeriodicRunner(evidence_provider=evidence, session_context_provider=lambda t: None,
                                   guardian_runner=GuardianRunner())
    scheduler = GuardianScheduler(runner=runner, clock=lambda: current[0], cadence=CADENCE,
                                  state_store=GuardianSchedulerStateStore(tmp_path))
    scheduler.poll = Mock(wraps=scheduler.poll)
    events = []
    waits = []
    def wait(delay):
        waits.append(delay)
        if len(waits) == 1: current[0] += timedelta(seconds=600)
        else: stop.set()
    host = GuardianHost(scheduler=scheduler, cadence=CADENCE, clock=lambda: current[0],
                        stop_event=stop, report=events.append, wait=wait)
    assert host.run() == 0
    assert scheduler.poll.call_count == 2
    assert evidence.call_args_list[1].args == (NOW + timedelta(seconds=600),)
    assert waits == [60, 60]


def test_actual_wait_interruptible():
    stop = Event()
    scheduler = Mock()
    scheduler.poll.return_value = Mock(slot=NOW, status=__import__('astropilot.guardian_scheduler',
        fromlist=['GuardianSchedulerStatus']).GuardianSchedulerStatus.SKIPPED,
        reason='slot_already_reserved', cycle=None)
    entered = Event()
    def report(event): entered.set()
    host = GuardianHost(scheduler=scheduler, cadence=CADENCE, clock=lambda: NOW,
                        stop_event=stop, report=report)
    thread = Thread(target=host.run)
    thread.start()
    try:
        assert entered.wait(2)
        stop.set()
        thread.join(2)
        assert not thread.is_alive()
    finally:
        stop.set()
        thread.join(2)
    scheduler.poll.assert_called_once()


def test_host_dependency_boundary():
    tree = ast.parse((Path(__file__).resolve().parents[2] / 'astropilot/guardian_host.py').read_text())
    allowed = {'astropilot.guardian_scheduler', 'astropilot.guardian_scheduler_state',
               'decision.runners.guardian_periodic_runner', 'decision.runners.guardian_runner'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): names = [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom): names = [node.module]
        else: continue
        assert all(n.split('.')[0] in sys.stdlib_module_names or n in allowed for n in names)


def _process_host(config_path, directory, queue):
    import astropilot.guardian_host as module
    module._emit = queue.put
    providers = GuardianHostProviders(lambda t: GuardianObservation(), lambda t: None)
    code = module.main(['--config', config_path, '--data-dir', directory],
                       provider_factories={'test': lambda: providers}, clock=lambda: NOW)
    queue.put({'exit_code': code})


@pytest.mark.skipif(__import__('os').name == 'nt', reason='POSIX process signals')
@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_real_process_signals_lock_and_restart(tmp_path, capsys, signum):
    import multiprocessing
    import os
    ctx = multiprocessing.get_context('spawn')
    queue = ctx.Queue()
    path = config(tmp_path)
    directory = tmp_path / 'État space'
    process = ctx.Process(target=_process_host, args=(str(path), str(directory), queue))
    process.start()
    try:
        assert queue.get(timeout=10)['event'] == 'startup'
        assert queue.get(timeout=10)['status'] == 'COMPLETED'
        factory = Mock()
        assert main(['--config', str(path), '--data-dir', str(directory), '--state-dir', str(tmp_path / 'other')],
                    provider_factories={'test': factory}) == 4
        factory.assert_not_called()
        capsys.readouterr()
        os.kill(process.pid, signum)
        assert queue.get(timeout=5) == {'event': 'shutdown'}
        assert queue.get(timeout=5) == {'exit_code': 0}
        process.join(5)
        assert process.exitcode == 0
        code, events = invoke(tmp_path, capsys)
        assert code == 0 and events[1]['reason'] == 'slot_already_reserved'
    finally:
        if process.is_alive(): process.terminate()
        process.join(5)
        queue.close()
        queue.join_thread()


def test_session_failure_never_emits_favorable_action(tmp_path, capsys):
    from decision.models.guardian import GuardianEvidence
    obs = GuardianObservation(**{k: GuardianEvidence(v, 'injected', 'OBSERVATION', NOW)
        for k, v in dict(rain_active=False, rain_eta_minutes=None, wind_kmh=0,
                        gust_kmh=0, humidity_percent=40, dew_spread_c=10).items()})
    providers = GuardianHostProviders(lambda t: obs, Mock(side_effect=RuntimeError('secret')))
    code, events = invoke(tmp_path, capsys, providers=providers)
    assert code == 6
    assert events[1]['risk'] == 'SAFE'
    assert events[1]['action'] == 'EMERGENCY_STOP'
    assert not events[1]['decision_eligible']
    assert events[1]['session_applicability'] == 'UNKNOWN'


def test_disabled_default_no_state_or_factory(tmp_path, capsys):
    path = config(tmp_path)
    doc = json.loads(path.read_text())
    del doc['enabled']
    del doc['provider']
    path.write_text(json.dumps(doc))
    factory = Mock()
    directory = tmp_path / 'not-created'
    assert main(['--config', str(path), '--data-dir', str(directory)], provider_factories={'test': factory}) == 0
    factory.assert_not_called()
    assert not directory.exists()
    assert [json.loads(line)['event'] for line in capsys.readouterr().out.splitlines()] == ['startup', 'shutdown']


def test_separate_state_dir_and_provider_output_allowlist(tmp_path, capsys):
    path = config(tmp_path)
    def evidence(time):
        print('private evidence')
        print('private failure', file=sys.stderr)
        return GuardianObservation()
    def factory():
        print('private factory')
        return GuardianHostProviders(evidence, lambda t: None)
    directory, state = tmp_path / 'data', tmp_path / 'state é space'
    assert main(['--config', str(path), '--data-dir', str(directory), '--state-dir', str(state), '--once'],
                provider_factories={'test': factory}, clock=lambda: NOW) == 0
    captured = capsys.readouterr()
    assert 'private' not in captured.out + captured.err
    assert (state / 'guardian_scheduler' / 'state.json').exists()
    assert {p.name for p in directory.iterdir()} == {'.guardian_host.lock'}


def test_before_anchor_once_and_clock_rollback(tmp_path):
    from astropilot.guardian_scheduler import GuardianSchedulerResult, GuardianSchedulerStatus
    stop = Event()
    current = [NOW - timedelta(seconds=10)]
    scheduler = Mock()
    scheduler.poll.side_effect = [GuardianSchedulerResult(GuardianSchedulerStatus.SKIPPED, None, 'before_anchor'),
        GuardianSchedulerResult(GuardianSchedulerStatus.SKIPPED, NOW, 'slot_already_reserved')]
    waits = []
    def wait(delay):
        waits.append(delay)
        if len(waits) == 1: current[0] = NOW
        elif len(waits) == 2: current[0] = NOW - timedelta(seconds=100)
        else: stop.set()
    host = GuardianHost(scheduler=scheduler, cadence=CADENCE, clock=lambda: current[0],
                        stop_event=stop, report=lambda e: None, wait=wait)
    assert host.run() == 0
    assert scheduler.poll.call_count == 2
    assert waits == [10, 60, 60]
    scheduler.poll.reset_mock(side_effect=True)
    scheduler.poll.return_value = GuardianSchedulerResult(GuardianSchedulerStatus.SKIPPED, None, 'before_anchor')
    stop.clear()
    assert host.run(once=True) == 0
    scheduler.poll.assert_called_once()


def test_no_network_or_child_process(tmp_path, capsys, monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs): raise AssertionError('unexpected external dependency')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    assert invoke(tmp_path, capsys)[0] == 0


def test_windows_host_lock_backend(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import astropilot.guardian_host as module
    calls = []
    fake = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0,
                          locking=lambda fd, mode, count: calls.append((mode, count)))
    monkeypatch.setitem(sys.modules, 'msvcrt', fake)
    monkeypatch.setattr(module, 'os', SimpleNamespace(name='nt'))
    with host_lock(tmp_path / '.guardian_host.lock'): pass
    assert calls == [(2, 1), (0, 1)]
    fake.locking = Mock(side_effect=BlockingIOError(11, 'busy'))
    with pytest.raises(HostAlreadyRunning):
        with host_lock(tmp_path / '.guardian_host.lock'): pytest.fail('duplicate accepted')
