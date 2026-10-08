import base64
from dataclasses import fields, replace
import inspect
import json
import subprocess
from threading import Event
from unittest.mock import Mock

import pytest
from test_opportunity_alerts_v1 import complete, policy
from test_modern_mission_authorization import assembly_environment
from test_opportunity_alert_notification_v1 import claimed
from astropilot.opportunity_alert_notification import NotificationPayload, DeliveryResult, DeliveryStatus, deliver_cycle, notification_text
from astropilot.opportunity_alert_windows_notification import WindowsNotifier
from astropilot.opportunity_alert_host import OpportunityAlertHost, load_config
from astropilot.opportunity_alert_ledger import FileOpportunityAlertLedger
from astropilot.opportunity_alert_scheduler import OpportunityAlertScheduler
from decision.runners.opportunity_alert_runner import OpportunityAlertRunner, OpportunityAlertCycleStatus


def backend(process, platform='win32', system_root=r'C:\Windows'):
    return WindowsNotifier(platform=platform, process=process, system_root=system_root)


def test_claim_delivers_once_with_same_public_payload(complete, policy, tmp_path):
    cycle, tonight = claimed(complete, policy, tmp_path)
    process = Mock(return_value=Mock(returncode=0))
    notifier = backend(process)
    payloads = []
    original = notifier.notify
    notifier.notify = lambda payload: (payloads.append(payload), original(payload))[1]
    assert deliver_cycle(cycle, notifier) == DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
    process.assert_called_once()
    assert payloads == [NotificationPayload.from_alert(cycle.alert)]
    assert {f.name for f in fields(payloads[0])} == {'project_key', 'site_name', 'window_start', 'window_end', 'expected_gain'}
    tonight.evaluate.assert_called_once()


@pytest.mark.parametrize('status', [OpportunityAlertCycleStatus.NO_ALERT, OpportunityAlertCycleStatus.ERROR])
def test_non_alert_never_launches_process(complete, policy, tmp_path, status):
    cycle, _ = claimed(complete, policy, tmp_path)
    process = Mock()
    assert deliver_cycle(replace(cycle, status=status, alert=None), backend(process)) is None
    process.assert_not_called()


@pytest.mark.parametrize('failure,reason', [
    (subprocess.TimeoutExpired('powershell', 20), 'delivery_timeout'),
    (FileNotFoundError('private path'), 'process_failed'),
    (PermissionError('private restriction'), 'process_failed'),
])
def test_failures_preserve_claim_and_restart_suppression(complete, policy, tmp_path, failure, reason):
    tonight = Mock()
    tonight.evaluate.return_value = complete
    process = Mock(side_effect=failure)
    reports = []
    def run():
        runner = OpportunityAlertRunner(tonight_service=tonight, ledger=FileOpportunityAlertLedger(tmp_path))
        scheduler = OpportunityAlertScheduler(runner=runner, directory=tmp_path / 'scheduler', clock=lambda: complete.timeline_start)
        return OpportunityAlertHost(scheduler=scheduler, policy=policy, clock=lambda: complete.timeline_start,
            stop_event=Event(), report=reports.append, notifier=backend(process)).run(once=True)
    assert run().cycle.status is OpportunityAlertCycleStatus.ALERT_EMITTED
    assert reports[-1] == {'event': 'notification', 'status': 'FAILED', 'reason': reason}
    before = (tmp_path / 'opportunity_alert_ledger.json').read_bytes()
    run()
    assert (tmp_path / 'opportunity_alert_ledger.json').read_bytes() == before
    process.assert_called_once()
    tonight.evaluate.assert_called_once()


@pytest.mark.parametrize('exit_code', [1, 2, -1, 5])
def test_native_rejection_nonzero_exit_is_failed(complete, policy, tmp_path, exit_code):
    cycle, _ = claimed(complete, policy, tmp_path)
    process = Mock(return_value=Mock(returncode=exit_code))
    assert deliver_cycle(cycle, backend(process)) == DeliveryResult(DeliveryStatus.FAILED, 'process_failed')
    process.assert_called_once()


@pytest.mark.parametrize('platform,root', [('darwin', r'C:\Windows'), ('linux', r'C:\Windows'), ('win32', ''), ('win32', 'relative')])
def test_unavailable_backend_never_launches(complete, policy, tmp_path, platform, root):
    cycle, _ = claimed(complete, policy, tmp_path)
    process = Mock()
    assert deliver_cycle(cycle, backend(process, platform, root)) == DeliveryResult(DeliveryStatus.FAILED, 'process_failed')
    process.assert_not_called()


def test_user_content_is_only_json_data_and_script_is_fixed(complete, policy, tmp_path):
    cycle, _ = claimed(complete, policy, tmp_path)
    process = Mock(return_value=Mock(returncode=0))
    notifier = backend(process)
    name = 'É 雲 😀 " \\ & < > ; $(Get-Process) `echo`'
    payload = replace(NotificationPayload.from_alert(cycle.alert), project_key=name, site_name=name)
    assert notifier.notify(payload).status is DeliveryStatus.DELIVERED
    argv = process.call_args.args[0]
    kwargs = process.call_args.kwargs
    assert argv[0] == r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    assert argv[1:-1] == ['-NoProfile', '-NonInteractive', '-Sta', '-WindowStyle', 'Hidden', '-EncodedCommand']
    script = base64.b64decode(argv[-1]).decode('utf-16-le')
    assert name not in script and name not in ' '.join(argv)
    assert json.loads(kwargs['input']) == list(notification_text(payload))
    assert kwargs['input'].isascii() and kwargs['encoding'] == 'ascii'
    assert kwargs['shell'] is False and kwargs['timeout'] == 20 and kwargs['check'] is False
    assert kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL
    notifier.notify(replace(payload, site_name='other'))
    assert process.call_args.args[0] == argv
    assert '[Console]::In.ReadToEnd()' in script
    assert 'Shell_NotifyIconW' in script and 'finally' in script
    assert 'Invoke-Expression' not in script and 'Start-Process' not in script


def test_utf16_limits_and_invalid_payload(complete, policy, tmp_path):
    cycle, _ = claimed(complete, policy, tmp_path)
    process = Mock(return_value=Mock(returncode=0))
    notifier = backend(process)
    assert notifier.notify(None) == DeliveryResult(DeliveryStatus.FAILED, 'invalid_payload')
    process.assert_not_called()
    payload = replace(NotificationPayload.from_alert(cycle.alert), project_key='😀' * 160, site_name='😀' * 160)
    assert notifier.notify(payload).status is DeliveryStatus.DELIVERED
    title, message = json.loads(process.call_args.kwargs['input'])
    assert len(title.encode('utf-16-le')) <= 126
    assert len(message.encode('utf-16-le')) <= 510
    assert 'AstroPilot' in title


@pytest.mark.parametrize('channel,class_name', [('disabled', 'DisabledNotifier'), ('macos', 'MacOSNotifier'), ('windows', 'WindowsNotifier')])
def test_config_and_dispatch(tmp_path, monkeypatch, channel, class_name):
    import astropilot.opportunity_alert_host as module
    path = tmp_path / 'host.json'
    doc = {'schema_version': 1, 'interval_seconds': 3600, 'policy': {}, 'availability': None}
    path.write_text(json.dumps(doc))
    assert load_config(path).notification_channel == 'disabled'
    path.write_text(json.dumps(dict(doc, notification_channel=channel)))
    assert load_config(path).notification_channel == channel
    backends = {name: Mock() for name in ('DisabledNotifier', 'MacOSNotifier', 'WindowsNotifier')}
    for name, mock in backends.items():
        monkeypatch.setattr(module, name, mock)
    assert module.main(['--config', str(path), '--data-dir', str(tmp_path / 'data'), '--once']) == 0
    for name, mock in backends.items():
        assert mock.call_count == (1 if name == class_name else 0)
        mock.return_value.notify.assert_not_called()


def test_windows_backend_has_no_business_dependencies():
    import ast
    import astropilot.opportunity_alert_windows_notification as module
    tree = ast.parse(inspect.getsource(module))
    assert {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} <= {
        '__future__', 'astropilot.opportunity_alert_notification'}
    assert {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} <= {
        'base64', 'json', 'ntpath', 'os', 'subprocess', 'sys'}


def test_windows_native_script_parse_and_struct_without_notification():
    """Harmless Windows-only check; never invoke Shell_NotifyIconW."""
    import ntpath
    import os
    import sys
    from astropilot.opportunity_alert_windows_notification import _WINDOWS_SCRIPT
    if sys.platform != 'win32':
        pytest.skip('native Windows PowerShell parsing and marshaling')
    source = _WINDOWS_SCRIPT.split("@'\n", 1)[1].split("\n'@", 1)[0]
    validation = r'''$ErrorActionPreference = 'Stop'
try {
    $doc = ConvertFrom-Json -InputObject ([Console]::In.ReadToEnd())
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseInput([string]$doc[0], [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw 'invalid_script' }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type -TypeDefinition ([string]$doc[1])
    $data = New-Object OpportunityBalloon+Data
    $size = [Runtime.InteropServices.Marshal]::SizeOf($data)
    $expected = if ([IntPtr]::Size -eq 8) { 976 } else { 956 }
    if ($size -ne $expected) { throw 'invalid_native_struct_size' }
    $method = [OpportunityBalloon].GetMethod('Shell_NotifyIconW')
    if ($null -eq $method) { throw 'missing_native_method' }
    exit 0
} catch { exit 1 }
'''
    executable = ntpath.join(os.environ['SystemRoot'], 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-Sta',
        '-EncodedCommand', base64.b64encode(validation.encode('utf-16-le')).decode('ascii')],
        input=json.dumps([_WINDOWS_SCRIPT, source], ensure_ascii=True), encoding='ascii',
        shell=False, timeout=20, capture_output=True, check=False)
    assert result.returncode == 0, 'Windows script parse/framework/native structure check failed'
