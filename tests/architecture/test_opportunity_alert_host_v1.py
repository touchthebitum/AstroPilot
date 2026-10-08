from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import Mock
import json
import pytest
from test_opportunity_alerts_v1 import complete, policy
from test_modern_mission_authorization import assembly_environment

from astropilot.opportunity_alert_host import (
    OpportunityAlertHost, PreparingTonightService, host_lock, HostAlreadyRunning,
    load_config, main,
)
from astropilot.opportunity_alert_scheduler import OpportunityAlertScheduler, SchedulerStatus, SchedulerCadence
from decision.models.opportunity_alert import OpportunityAlertPolicy
from decision.runners.opportunity_alert_runner import OpportunityAlertRunner, OpportunityAlertCycleStatus

START = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def config_file(tmp_path, **overrides):
    path = tmp_path / 'host.json'
    doc = {'schema_version': 1, 'interval_seconds': 3600, 'policy': {}, 'availability': None}
    doc.update(overrides)
    path.write_text(json.dumps(doc))
    return path


def test_config_disabled_and_strict(tmp_path):
    config = load_config(config_file(tmp_path))
    assert not config.policy.enabled
    assert config.cadence.interval == timedelta(hours=1)
    for overrides in ({'extra': 1}, {'interval_seconds': True}, {'interval_seconds': 0},
            {'interval_seconds': 1.5}, {'schema_version': 2}, {'policy': {'enabled': 'true'}},
            {'policy': {'unknown': 1}}, {'availability': {'mode': 'all_night', 'start': '2026-10-08T12:00:00'}}):
        with pytest.raises(ValueError):
            load_config(config_file(tmp_path, **overrides))
    path = config_file(tmp_path)
    path.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError):
        load_config(path)


def test_lazy_preparation_disabled_and_repeated(tmp_path):
    profile, weather, tonight = Mock(), Mock(), Mock()
    service = PreparingTonightService(profile_provider=profile, weather_provider=weather,
        tonight_factory=lambda: tonight, availability=None)
    runner = OpportunityAlertRunner(tonight_service=service, ledger=Mock())
    scheduler = OpportunityAlertScheduler(runner=runner, directory=tmp_path, clock=lambda: START)
    assert scheduler.poll(policy=OpportunityAlertPolicy()).cycle.status is OpportunityAlertCycleStatus.NO_ALERT
    assert scheduler.poll(policy=OpportunityAlertPolicy()).status is SchedulerStatus.SKIPPED
    profile.assert_not_called()
    weather.assert_not_called()
    tonight.evaluate.assert_not_called()


def test_serial_loop_clock_jumps_and_stop():
    now = START
    stop = Event()
    scheduler = Mock()
    scheduler.cadence = SchedulerCadence()
    reports = []
    calls = []
    def poll(**kwargs):
        calls.append(kwargs['now'])
        # First cycle lasts several slots, then a later cycle requests shutdown.
        nonlocal now
        now += timedelta(hours=5) if len(calls) == 1 else timedelta(hours=1)
        if len(calls) == 2:
            stop.set()
        return Mock(status=SchedulerStatus.SKIPPED, slot=kwargs['now'], cycle=None, reason='test')
    scheduler.poll.side_effect = poll
    def wait(seconds):
        assert 0 < seconds <= 60
        nonlocal now
        now += timedelta(seconds=seconds)
        return False
    host = OpportunityAlertHost(scheduler=scheduler, policy=OpportunityAlertPolicy(),
        clock=lambda: now, stop_event=stop, wait=wait, report=reports.append)
    host.run()
    assert calls == [START, START + timedelta(hours=5)]
    assert len(reports) == 2


def test_stop_before_start_skips_poll():
    scheduler, stop = Mock(), Event()
    stop.set()
    OpportunityAlertHost(scheduler=scheduler, policy=OpportunityAlertPolicy(),
        clock=lambda: START, stop_event=stop, report=Mock()).run()
    scheduler.poll.assert_not_called()


def test_lifetime_lock(tmp_path):
    with host_lock(tmp_path / 'host.lock'):
        with pytest.raises(HostAlreadyRunning):
            with host_lock(tmp_path / 'host.lock'):
                pytest.fail('duplicate host admitted')
    with host_lock(tmp_path / 'host.lock'):
        pass


def test_cli_once_disabled_and_invalid(tmp_path, capsys):
    data = tmp_path / 'user'
    path = config_file(tmp_path)
    assert main(['--config', str(path), '--data-dir', str(data), '--once']) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [line['event'] for line in lines] == ['startup', 'cycle', 'shutdown']
    assert lines[1]['cycle_status'] == 'NO_ALERT'
    assert not (data / 'user_profile.json').exists()
    assert not (data / 'opportunity_alert_ledger.json').exists()
    assert main(['--config', str(config_file(tmp_path, interval_seconds=0)),
        '--data-dir', str(tmp_path / 'invalid'), '--once']) == 1
    assert not (tmp_path / 'invalid').exists()


@pytest.mark.parametrize('mode,extra', [
    ('all_night', {}), ('duration', {'duration_seconds': 7200}),
    ('start_and_duration', {'start': START.isoformat(), 'duration_seconds': 7200}),
    ('until', {'end': (START + timedelta(hours=2)).isoformat()}),
    ('fixed_window', {'start': START.isoformat(), 'end': (START + timedelta(hours=2)).isoformat()}),
])
def test_explicit_enabled_configuration(tmp_path, mode, extra):
    enabled = {'enabled': True, 'site_name': 'Buttes', 'project_keys': ['Sh2-129'],
        'intent_ids': ['sh2-129_ha'], 'filter_profile_ids': ['explicit-profile']}
    config = load_config(config_file(tmp_path, policy=enabled, availability={'mode': mode, **extra}))
    assert config.policy.enabled
    assert config.availability.mode.value == mode
    with pytest.raises(ValueError):
        load_config(config_file(tmp_path, policy=enabled))


def valid_profile():
    return {'active_equipment': 'samyang_183', 'available_equipment': ['samyang_183'],
        'location': {'name': 'Buttes', 'latitude': 46.75, 'longitude': 6.55},
        'preferences': {'bortle': 4}}


def test_preparation_once_and_error_next_slot(tmp_path):
    from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
    from decision.services.tonight_application_service import TonightResult, TonightStatus
    profile, weather, factory, tonight = Mock(), Mock(), Mock(), Mock()
    profile.return_value = valid_profile()
    availability = SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)
    factory.return_value = tonight
    tonight.evaluate.return_value = TonightResult(None, None, None, status=TonightStatus.NO_NIGHT)
    adapter = PreparingTonightService(profile_provider=profile, weather_provider=weather,
        tonight_factory=factory, availability=availability)
    ledger = Mock()
    runner = OpportunityAlertRunner(tonight_service=adapter, ledger=ledger)
    scheduler = OpportunityAlertScheduler(runner=runner, directory=tmp_path, clock=lambda: START)
    enabled = OpportunityAlertPolicy(enabled=True, site_name='Buttes', project_keys=('Sh2-129',),
        intent_ids=('sh2-129_ha',), filter_profile_ids=('explicit',))
    profile.side_effect = RuntimeError('private profile data')
    failed = scheduler.poll(policy=enabled)
    assert failed.cycle.status is OpportunityAlertCycleStatus.ERROR
    weather.assert_not_called()
    assert scheduler.poll(policy=enabled).status is SchedulerStatus.SKIPPED
    profile.side_effect = None
    result = scheduler.poll(policy=enabled, now=START + timedelta(hours=1))
    assert result.cycle.status is OpportunityAlertCycleStatus.NO_ALERT
    weather.assert_called_once_with(46.75, 6.55)
    factory.assert_called_once_with()
    tonight.evaluate.assert_called_once_with(profile=profile.return_value, weather=weather.return_value,
        reference_time_utc=START + timedelta(hours=1), bortle=4, equipment='samyang_183', availability=availability)
    ledger.claim.assert_not_called()


def test_backward_clock_and_interruptible_wait():
    scheduler = Mock()
    scheduler.cadence = SchedulerCadence()
    scheduler.poll.return_value = Mock(status=SchedulerStatus.SKIPPED, slot=START, reason='test', cycle=None)
    now = START
    stop = Event()
    waits = []
    def wait(seconds):
        waits.append(seconds)
        nonlocal now
        if len(waits) == 1:
            now = START - timedelta(hours=3)
        else:
            stop.set()
        return stop.is_set()
    OpportunityAlertHost(scheduler=scheduler, policy=OpportunityAlertPolicy(), clock=lambda: now,
        stop_event=stop, wait=wait, report=Mock()).run()
    scheduler.poll.assert_called_once()
    assert waits == [60, 60]


def test_shutdown_finishes_active_cycle():
    from astropilot.opportunity_alert_host import shutdown_signals
    import signal
    old_int, old_term = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
    scheduler, stop = Mock(), Event()
    scheduler.cadence = SchedulerCadence()
    reports = []
    def poll(**kwargs):
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        return Mock(status=SchedulerStatus.COMPLETED, slot=START, reason='cycle_completed', cycle=None)
    scheduler.poll.side_effect = poll
    with shutdown_signals(stop):
        OpportunityAlertHost(scheduler=scheduler, policy=OpportunityAlertPolicy(), clock=lambda: START,
            stop_event=stop, report=reports.append).run()
    assert len(reports) == 1
    assert signal.getsignal(signal.SIGINT) == old_int
    assert signal.getsignal(signal.SIGTERM) == old_term


def test_cli_errors_and_environment_restored(tmp_path, monkeypatch, capsys):
    import os
    import astropilot.opportunity_alert_host as module
    enabled = {'enabled': True, 'site_name': 'Buttes', 'project_keys': ['Sh2-129'],
        'intent_ids': ['sh2-129_ha'], 'filter_profile_ids': ['explicit']}
    path = config_file(tmp_path, policy=enabled, availability={'mode': 'all_night'})
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', 'previous')
    monkeypatch.setattr(module, '_profile', Mock(side_effect=RuntimeError('sensitive')))
    monkeypatch.setattr(module, '_weather', Mock())
    data = tmp_path / 'user'
    assert main(['--config', str(path), '--data-dir', str(data), '--once']) == 1
    assert os.environ['ASTROPILOT_DATA_DIR'] == 'previous'
    assert 'sensitive' not in capsys.readouterr().out
    module._weather.assert_not_called()
    with host_lock(data / '.opportunity_alert_host.lock'):
        assert main(['--config', str(path), '--data-dir', str(data), '--once']) == 1
    assert 'already_running' in capsys.readouterr().out


def test_dependency_boundary():
    import ast
    import inspect
    import astropilot.opportunity_alert_host as module
    tree = ast.parse(inspect.getsource(module))
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {'__future__', 'contextlib', 'dataclasses', 'datetime', 'pathlib', 'threading',
        'astropilot.opportunity_alert_ledger', 'astropilot.opportunity_alert_scheduler',
        'astropilot.opportunity_alert_notification', 'astropilot.opportunity_alert_windows_notification',
        'decision.models.opportunity_alert', 'decision.models.session_availability',
        'decision.runners.opportunity_alert_runner', 'decision.services.tonight_application_service',
        'astropilot.user_profile', 'astro_score'}
    astro_names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        and n.module == 'astro_score' for a in n.names}
    assert astro_names == {'fetch_weather', 'build_tonight_application_service'}
    assert 'requests' not in inspect.getsource(module)


def test_real_process_shutdown_duplicate_and_restart(tmp_path):
    import os
    import select
    import signal
    import subprocess
    import sys
    if os.name == 'nt':
        pytest.skip('POSIX SIGTERM subprocess smoke; portable signal restoration tested separately')
    config = config_file(tmp_path)
    command = [sys.executable, '-m', 'astropilot.opportunity_alert_host', '--config', str(config),
        '--data-dir', str(tmp_path / 'user')]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 15)[0], 'host startup timed out'
        assert json.loads(process.stdout.readline())['event'] == 'startup'
        # The cycle may already be buffered; communicate after shutdown collects the remaining lines.
        duplicate = subprocess.run(command + ['--once'], capture_output=True, text=True, timeout=15)
        assert duplicate.returncode == 1
        assert 'already_running' in duplicate.stdout
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        events = [json.loads(line) for line in stdout.splitlines()]
        assert events[-1]['event'] == 'shutdown'
        assert any(e.get('cycle_status') == 'NO_ALERT' for e in events)
        restarted = subprocess.run(command + ['--once'], capture_output=True, text=True, timeout=15)
        assert restarted.returncode == 0, restarted.stderr
        assert 'SKIPPED' in restarted.stdout
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_real_alert_host_restart_and_ledger(complete, policy, tmp_path, capsys):
    from astropilot.opportunity_alert_ledger import FileOpportunityAlertLedger
    from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
    from astropilot.opportunity_alert_host import cycle_diagnostic
    at = complete.timeline_start
    profile, weather, tonight = Mock(), Mock(), Mock()
    profile.return_value = valid_profile()
    def forecast(*args):
        print('legacy provider private diagnostics')
        return object()
    weather.side_effect = forecast
    tonight.evaluate.return_value = complete
    def build():
        runner = OpportunityAlertRunner(tonight_service=PreparingTonightService(
            profile_provider=profile, weather_provider=weather, tonight_factory=lambda: tonight,
            availability=SessionAvailability(SessionAvailabilityMode.ALL_NIGHT)),
            ledger=FileOpportunityAlertLedger(tmp_path))
        return OpportunityAlertScheduler(runner=runner, directory=tmp_path / 'scheduler', clock=lambda: at)
    first = build().poll(policy=policy)
    assert first.cycle.status is OpportunityAlertCycleStatus.ALERT_EMITTED
    assert capsys.readouterr().out == ''
    assert set(cycle_diagnostic(first)) == {'event', 'slot', 'status', 'reason', 'cycle_status', 'logical_time'}
    assert build().poll(policy=policy).status is SchedulerStatus.SKIPPED
    from test_opportunity_alert_runner_v1 import shift
    tonight.evaluate.return_value = shift(complete, timedelta(hours=1), 'next-host-slot')
    future = build().poll(policy=policy, now=at + timedelta(hours=1))
    assert future.cycle.status is OpportunityAlertCycleStatus.NO_ALERT
    assert future.cycle.reason_codes == ('duplicate_or_cooldown',)
    assert profile.call_count == weather.call_count == tonight.evaluate.call_count == 2
    assert first.cycle.alert is not None


def test_invalid_config_nonfinite_and_naive(tmp_path):
    path = config_file(tmp_path)
    for doc in (
        {'schema_version': 1, 'interval_seconds': 3600, 'policy': {'min_quality': float('nan')}, 'availability': None},
        {'schema_version': 1, 'interval_seconds': 3600, 'policy': {'window_start': '2026-10-08T12:00:00'}, 'availability': None},
        {'schema_version': 1, 'interval_seconds': 3600, 'policy': {}, 'availability': {'mode': 'duration', 'duration_seconds': True}},
    ):
        path.write_text(json.dumps(doc))
        with pytest.raises(ValueError):
            load_config(path)


def test_mid_slot_fresh_weather_uses_live_time(tmp_path):
    from types import SimpleNamespace
    from decision.weather.weather_ingress import validate_weather_freshness
    from decision.services.tonight_application_service import TonightResult, TonightStatus
    live = START + timedelta(minutes=45)
    weather = SimpleNamespace(retrieved_at_utc=live + timedelta(seconds=15))
    def evaluate(**inputs):
        # The existing freshness gate rejects the old slot-start reference here.
        validate_weather_freshness(inputs['weather'], reference_time_utc=inputs['reference_time_utc'])
        assert inputs['reference_time_utc'] == live
        return TonightResult(None, None, None, status=TonightStatus.NO_NIGHT)
    tonight = Mock()
    tonight.evaluate.side_effect = evaluate
    adapter = PreparingTonightService(profile_provider=valid_profile,
        weather_provider=lambda *_: weather, tonight_factory=lambda: tonight, availability=None)
    runner = OpportunityAlertRunner(tonight_service=adapter, ledger=Mock())
    s = OpportunityAlertScheduler(runner=runner, directory=tmp_path, clock=lambda: live)
    enabled = OpportunityAlertPolicy(enabled=True, site_name='Buttes', project_keys=('Sh2-129',),
        intent_ids=('sh2-129_ha',), filter_profile_ids=('explicit',))
    reports = []
    result = OpportunityAlertHost(scheduler=s, policy=enabled, clock=lambda: live,
        stop_event=Event(), report=reports.append).run(once=True)
    assert result.slot == START
    assert result.cycle.logical_time == live
    assert result.cycle.status is OpportunityAlertCycleStatus.NO_ALERT
    assert reports[0]['logical_time'] == live.isoformat()
    tonight.evaluate.assert_called_once()


def test_weather_unavailable_has_no_hidden_retry(tmp_path):
    weather, factory = Mock(return_value=None), Mock()
    adapter = PreparingTonightService(profile_provider=valid_profile,
        weather_provider=weather, tonight_factory=factory, availability=None)
    runner = OpportunityAlertRunner(tonight_service=adapter, ledger=Mock())
    scheduler = OpportunityAlertScheduler(runner=runner, directory=tmp_path, clock=lambda: START)
    enabled = OpportunityAlertPolicy(enabled=True, site_name='Buttes', project_keys=('Sh2-129',),
        intent_ids=('sh2-129_ha',), filter_profile_ids=('explicit',))
    first = scheduler.poll(policy=enabled, cycle_time=START)
    assert first.cycle.status is OpportunityAlertCycleStatus.ERROR
    assert not first.cycle.evaluated
    assert scheduler.poll(policy=enabled).status is SchedulerStatus.SKIPPED
    weather.assert_called_once()
    factory.assert_not_called()
