from dataclasses import fields, replace
from datetime import timedelta
from threading import Event
from unittest.mock import Mock
import inspect
import subprocess

import pytest
from test_opportunity_alerts_v1 import complete, policy
from test_modern_mission_authorization import assembly_environment

from astropilot.opportunity_alert_notification import (
    NotificationPayload, DeliveryStatus, DeliveryResult, DisabledNotifier,
    MacOSNotifier, deliver_cycle, notification_text,
)
from astropilot.opportunity_alert_host import OpportunityAlertHost, load_config
from astropilot.opportunity_alert_ledger import FileOpportunityAlertLedger
from astropilot.opportunity_alert_scheduler import OpportunityAlertScheduler
from decision.runners.opportunity_alert_runner import OpportunityAlertRunner, OpportunityAlertCycleStatus


def claimed(complete, policy, tmp_path):
    tonight = Mock()
    tonight.evaluate.return_value = complete
    runner = OpportunityAlertRunner(tonight_service=tonight, ledger=FileOpportunityAlertLedger(tmp_path))
    return runner.run_cycle(policy=policy, logical_time=complete.timeline_start), tonight


def test_projection_and_single_delivery(complete, policy, tmp_path):
    cycle, tonight = claimed(complete, policy, tmp_path)
    notifier = Mock()
    notifier.notify.return_value = DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
    assert deliver_cycle(cycle, notifier).status is DeliveryStatus.DELIVERED
    notifier.notify.assert_called_once()
    payload = notifier.notify.call_args.args[0]
    assert {f.name for f in fields(payload)} == {
        'project_key', 'site_name', 'window_start', 'window_end', 'expected_gain'}
    assert payload == NotificationPayload.from_alert(cycle.alert)
    tonight.evaluate.assert_called_once()


@pytest.mark.parametrize('status', [OpportunityAlertCycleStatus.NO_ALERT, OpportunityAlertCycleStatus.ERROR])
def test_non_alert_never_notifies(complete, policy, tmp_path, status):
    cycle, _ = claimed(complete, policy, tmp_path)
    notifier = Mock()
    assert deliver_cycle(replace(cycle, status=status, alert=None), notifier) is None
    assert deliver_cycle(None, notifier) is None
    notifier.notify.assert_not_called()


@pytest.mark.parametrize('failure,reason', [
    (subprocess.TimeoutExpired('osascript', 5), 'delivery_timeout'),
    (OSError('private diagnostics'), 'process_failed'),
])
def test_failed_process_preserves_ledger(complete, policy, tmp_path, failure, reason):
    cycle, _ = claimed(complete, policy, tmp_path)
    path = tmp_path / 'opportunity_alert_ledger.json'
    before = path.read_bytes()
    process = Mock(side_effect=failure)
    result = deliver_cycle(cycle, MacOSNotifier(platform='darwin', process=process))
    assert result == DeliveryResult(DeliveryStatus.FAILED, reason)
    assert path.read_bytes() == before
    process.assert_called_once()


def test_nonzero_disabled_and_platform(complete, policy, tmp_path):
    cycle, _ = claimed(complete, policy, tmp_path)
    process = Mock(return_value=Mock(returncode=1))
    assert deliver_cycle(cycle, MacOSNotifier(platform='darwin', process=process)).status is DeliveryStatus.FAILED
    process.reset_mock()
    assert deliver_cycle(cycle, MacOSNotifier(platform='win32', process=process)).status is DeliveryStatus.SKIPPED
    assert deliver_cycle(cycle, DisabledNotifier()).status is DeliveryStatus.SKIPPED
    process.assert_not_called()


def test_unicode_and_injection_are_only_arguments(complete, policy, tmp_path):
    cycle, _ = claimed(complete, policy, tmp_path)
    name = 'Étoile " \\ $(touch /tmp/never) `echo` ; 雲'
    cycle = replace(cycle, alert=replace(cycle.alert, project_key=name, site_name=name))
    process = Mock(return_value=Mock(returncode=0))
    assert deliver_cycle(cycle, MacOSNotifier(platform='darwin', process=process)).status is DeliveryStatus.DELIVERED
    args, kwargs = process.call_args
    assert args[0][:2] == ['/usr/bin/osascript', '-']
    assert args[0][2:] == list(notification_text(NotificationPayload.from_alert(cycle.alert)))
    assert name not in kwargs['input']
    assert kwargs['shell'] is False and kwargs['timeout'] == 5
    assert kwargs['encoding'] == 'utf-8'
    assert kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL


def test_failed_notifier_is_sanitized(complete, policy, tmp_path):
    cycle, _ = claimed(complete, policy, tmp_path)
    notifier = Mock()
    notifier.notify.side_effect = RuntimeError('private evidence')
    assert deliver_cycle(cycle, notifier) == DeliveryResult(DeliveryStatus.FAILED, 'notifier_failed')
    notifier.notify.side_effect = None
    notifier.notify.return_value = None
    assert deliver_cycle(cycle, notifier).status is DeliveryStatus.FAILED
    invalid = replace(cycle, alert=replace(cycle.alert, expected_gain=float('nan')))
    notifier.reset_mock()
    assert deliver_cycle(invalid, notifier).status is DeliveryStatus.FAILED
    notifier.notify.assert_not_called()


def test_host_restart_suppression_and_failure_continuation(complete, policy, tmp_path):
    from test_opportunity_alert_runner_v1 import shift
    tonight = Mock()
    tonight.evaluate.return_value = complete
    notifier = Mock()
    notifier.notify.side_effect = RuntimeError('private')
    def run(at):
        runner = OpportunityAlertRunner(tonight_service=tonight, ledger=FileOpportunityAlertLedger(tmp_path))
        scheduler = OpportunityAlertScheduler(runner=runner, directory=tmp_path / 'scheduler', clock=lambda: at)
        reports = []
        result = OpportunityAlertHost(scheduler=scheduler, policy=policy, clock=lambda: at,
            stop_event=Event(), report=reports.append, notifier=notifier).run(once=True)
        return result, reports
    first, reports = run(complete.timeline_start)
    assert first.cycle.status is OpportunityAlertCycleStatus.ALERT_EMITTED
    assert reports[-1] == {'event': 'notification', 'status': 'FAILED', 'reason': 'notifier_failed'}
    ledger = (tmp_path / 'opportunity_alert_ledger.json').read_bytes()
    run(complete.timeline_start)
    tonight.evaluate.return_value = shift(complete, timedelta(hours=1), 'notification-next')
    result, reports = run(complete.timeline_start + timedelta(hours=1))
    assert result.cycle.status is OpportunityAlertCycleStatus.NO_ALERT
    assert len(reports) == 1
    notifier.notify.assert_called_once()
    import json
    after = json.loads((tmp_path / 'opportunity_alert_ledger.json').read_bytes())
    before = json.loads(ledger)
    assert after['entries'] == before['entries']
    assert after['families'] == before['families']
    assert tonight.evaluate.call_count == 2


def test_channel_config(tmp_path):
    import json
    doc = {'schema_version': 1, 'interval_seconds': 3600, 'policy': {}, 'availability': None}
    path = tmp_path / 'host.json'
    for channel in ('disabled', 'macos'):
        path.write_text(json.dumps(dict(doc, notification_channel=channel)))
        assert load_config(path).notification_channel == channel
    for channel in ('email', None, True, []):
        path.write_text(json.dumps(dict(doc, notification_channel=channel)))
        with pytest.raises(ValueError):
            load_config(path)


def test_delivery_dependency_boundary():
    import ast
    import astropilot.opportunity_alert_notification as module
    tree = ast.parse(inspect.getsource(module))
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports <= {'__future__', 'dataclasses', 'datetime', 'enum', 'typing',
        'decision.models.opportunity_alert', 'decision.runners.opportunity_alert_runner'}
    assert {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} <= {'math', 'subprocess', 'sys'}


def test_scheduler_error_after_claim_still_delivers(complete, policy, tmp_path):
    from astropilot.opportunity_alert_scheduler import SchedulerResult, SchedulerStatus, SchedulerCadence
    cycle, _ = claimed(complete, policy, tmp_path)
    scheduler = Mock(cadence=SchedulerCadence())
    scheduler.poll.return_value = SchedulerResult(SchedulerStatus.ERROR, complete.timeline_start,
        'scheduler_state_unavailable', cycle)
    notifier = Mock()
    notifier.notify.return_value = DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
    reports = []
    OpportunityAlertHost(scheduler=scheduler, policy=policy, clock=lambda: complete.timeline_start,
        stop_event=Event(), report=reports.append, notifier=notifier).run(once=True)
    notifier.notify.assert_called_once()
    assert reports[-1]['status'] == 'DELIVERED'


def test_cli_opt_in_selects_backend(tmp_path, monkeypatch, capsys):
    import json
    import astropilot.opportunity_alert_host as module
    path = tmp_path / 'host.json'
    path.write_text(json.dumps({'schema_version': 1, 'interval_seconds': 3600,
        'policy': {}, 'availability': None, 'notification_channel': 'macos'}))
    backend = Mock()
    monkeypatch.setattr(module, 'MacOSNotifier', backend)
    assert module.main(['--config', str(path), '--data-dir', str(tmp_path / 'data'), '--once']) == 0
    backend.assert_called_once_with()
    backend.return_value.notify.assert_not_called()
    assert 'notification' not in capsys.readouterr().out


def test_native_argv_roundtrip_without_notification():
    import sys
    if sys.platform != 'darwin':
        pytest.skip('native macOS argument parsing')
    values = ['-- title Étoile " \\ $(never) `never` ; 雲', 'message — unicode']
    script = 'on run argv\n return (item 1 of argv) & linefeed & (item 2 of argv)\nend run\n'
    result = subprocess.run(['/usr/bin/osascript', '-', *values], input=script,
        encoding='utf-8', capture_output=True, timeout=5, check=True)
    assert result.stdout.rstrip('\n') == '\n'.join(values)
