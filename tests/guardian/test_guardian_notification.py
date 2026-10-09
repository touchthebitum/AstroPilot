from dataclasses import replace, fields
from datetime import datetime, timezone, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
import ast
from pathlib import Path
import subprocess
import sys
import pytest

from astropilot.guardian_notification import (
    GuardianNotificationPolicy, GuardianNotifier, NotificationPayload,
    DeliveryStatus, DeliveryResult, deliver_cycle, notification_text,
)
from astropilot.local_notification import MacOSChannel, WindowsChannel
from decision.models.guardian import GuardianObservation, GuardianRiskLevel, GuardianAction
from decision.models.guardian_cycle import GuardianCycleResult, GuardianCycleStatus
from decision.services.guardian_service import assess_guardian

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)
def cycle(level=GuardianRiskLevel.UNKNOWN):
    assessment = assess_guardian(GuardianObservation(), now=NOW)
    return GuardianCycleResult(GuardianCycleStatus.ASSESSED, NOW,
        replace(assessment, risk_level=level, action=GuardianAction(level.value)))

@pytest.mark.parametrize('level', list(GuardianRiskLevel))
@pytest.mark.parametrize('minimum', list(GuardianRiskLevel))
def test_explicit_policy(level, minimum):
    channel = Mock()
    channel.deliver.return_value = DeliveryResult(DeliveryStatus.DELIVERED, 'accepted_by_os')
    result = deliver_cycle(cycle(level), GuardianNotifier(channel, GuardianNotificationPolicy(True, minimum)))
    assert result.status is (DeliveryStatus.DELIVERED if level >= minimum else DeliveryStatus.SKIPPED)
    assert channel.deliver.call_count == int(level >= minimum)
    channel.reset_mock()
    assert deliver_cycle(cycle(level), GuardianNotifier(channel)).status is DeliveryStatus.SKIPPED
    channel.deliver.assert_not_called()

@pytest.mark.parametrize('failure', [RuntimeError('secret /path'), subprocess.TimeoutExpired('secret', 5)])
def test_failure_preserves_cycle(failure):
    original = cycle()
    channel = Mock(deliver=Mock(side_effect=failure))
    assert deliver_cycle(original, GuardianNotifier(channel, GuardianNotificationPolicy(True))).status is DeliveryStatus.FAILED
    assert original == cycle()
    channel.deliver.assert_called_once()


def test_payload_wording_and_allowlist():
    original = cycle()
    original = replace(original, assessment=replace(original.assessment,
        reasons=('wind_kmh:WARNING', '/secret', 'traceback', 'wind_kmh:WARNING')))
    payload = NotificationPayload.from_cycle(original)
    assert payload.reasons == ('wind_kmh:WARNING',)
    assert {f.name for f in fields(payload)} == {'risk_level','recommended_action','session_state',
        'action_applicability','reasons','assessed_at','logical_time'}
    title, text = notification_text(payload)
    assert 'UNKNOWN' in title and 'EMERGENCY_STOP' in text and 'uncertain' in text
    assert 'No action executed' in text and '/secret' not in text

@pytest.mark.parametrize('channel_type,platform,timeout', [(MacOSChannel,'darwin',5),(WindowsChannel,'win32',20)])
@pytest.mark.parametrize('outcome,status', [(0,DeliveryStatus.DELIVERED),(1,DeliveryStatus.FAILED),('timeout',DeliveryStatus.FAILED)])
def test_os_semantics(channel_type, platform, timeout, outcome, status):
    process = Mock(return_value=SimpleNamespace(returncode=outcome))
    if outcome == 'timeout': process.side_effect = subprocess.TimeoutExpired('private', timeout)
    options = {'system_root': r'C:\Windows'} if channel_type is WindowsChannel else {}
    channel = channel_type(platform=platform, process=process, **options)
    result = channel.deliver('Guardian é " $(touch /tmp/x) ☄', 'Quotes \' ` & < > ; \\ Unicode 🪐')
    assert result.status is status
    args, kw = process.call_args
    assert kw['shell'] is False and kw['timeout'] == timeout
    assert kw['stdout'] == kw['stderr'] == subprocess.DEVNULL
    if platform == 'darwin':
        assert args[0][2].startswith('Guardian é')
        assert 'touch' not in kw['input']
    else:
        assert 'EncodedCommand' in ' '.join(args[0])
        assert 'touch' not in ' '.join(args[0])
        assert 'Guardian' in kw['input']


def test_restart_same_slot_not_notified_twice(tmp_path):
    from astropilot.guardian_host import GuardianHost
    from astropilot.guardian_scheduler import GuardianScheduler, GuardianSchedulerCadence
    from astropilot.guardian_scheduler_state import GuardianSchedulerStateStore
    cadence = GuardianSchedulerCadence(timedelta(seconds=60), NOW)
    runner = Mock(run_cycle=Mock(return_value=cycle()))
    channel = Mock(deliver=Mock(return_value=DeliveryResult(DeliveryStatus.FAILED,'process_failed')))
    notifier = GuardianNotifier(channel, GuardianNotificationPolicy(True))
    for _ in range(2):
        scheduler = GuardianScheduler(runner=runner, clock=lambda:NOW, cadence=cadence,
            state_store=GuardianSchedulerStateStore(tmp_path))
        host = GuardianHost(scheduler=scheduler,cadence=cadence,clock=lambda:NOW,
            stop_event=Event(),report=lambda e:None,notifier=notifier)
        assert host.run(once=True) == 0
    channel.deliver.assert_called_once()
    runner.run_cycle.assert_called_once()


def test_notification_dependency_boundary():
    root = Path(__file__).resolve().parents[2]
    allowed = {'decision.models.guardian','decision.models.guardian_cycle',
               'astropilot.local_notification','astropilot.guardian_notification'}
    for filename in ('guardian_notification.py','local_notification.py'):
        tree = ast.parse((root/'astropilot'/filename).read_text())
        for n in ast.walk(tree):
            if isinstance(n,ast.Import): names=[x.name for x in n.names]
            elif isinstance(n,ast.ImportFrom): names=[n.module]
            else: continue
            assert all(x.split('.')[0] in sys.stdlib_module_names or x in allowed for x in names)


def test_windows_native_script_parse_and_struct_without_notification():
    """Harmless Windows-only check; never invoke Shell_NotifyIconW."""
    import base64
    import json
    import ntpath
    import os
    import sys
    from astropilot.local_notification import _WINDOWS_SCRIPT
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
    $data = New-Object LocalBalloon+Data
    $size = [Runtime.InteropServices.Marshal]::SizeOf($data)
    $expected = if ([IntPtr]::Size -eq 8) { 976 } else { 956 }
    if ($size -ne $expected) { throw 'invalid_native_struct_size' }
    $method = [LocalBalloon].GetMethod('Shell_NotifyIconW')
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


@pytest.mark.parametrize('doc', [None, [], {'enabled':1}, {'min_level':'bogus'},
    {'min_level':True}, {'version':'v2'}, {'channel':'email'}, {'secret':'/path'}])
def test_invalid_policy(doc):
    with pytest.raises(ValueError): GuardianNotificationPolicy.from_config(doc)


def test_policy_config_and_main(tmp_path, monkeypatch, capsys):
    import json
    import astropilot.guardian_host as host
    from astropilot.guardian_host import GuardianHostProviders
    doc = dict(schema_version=1,enabled=True,interval_seconds=60,anchor=NOW.isoformat(),
        provider='test',notification={'enabled':True,'min_level':'WATCH','version':'guardian-notification-v1'})
    path = tmp_path/'config.json'
    path.write_text(json.dumps(doc))
    channel = Mock(deliver=Mock(return_value=DeliveryResult(DeliveryStatus.DELIVERED,'accepted_by_os')))
    monkeypatch.setattr(host,'local_notifier',lambda policy:GuardianNotifier(channel,policy))
    for _ in range(2):
        assert host.main(['--config',str(path),'--data-dir',str(tmp_path),'--once'],
            provider_factories={'test':lambda:GuardianHostProviders(lambda t:GuardianObservation(),lambda t:None)},
            clock=lambda:NOW) == 0
    channel.deliver.assert_called_once()
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e for e in events if e['event']=='notification'] == [
        {'event':'notification','status':'DELIVERED','reason':'accepted_by_os'}]


def test_no_service_reentry(monkeypatch):
    import decision.services.guardian_service as service
    original = cycle()
    monkeypatch.setattr(service,'assess_guardian',lambda *a,**kw:pytest.fail('evaluation called'))
    channel = Mock(deliver=Mock(return_value=DeliveryResult(DeliveryStatus.DELIVERED,'accepted_by_os')))
    assert deliver_cycle(original,GuardianNotifier(channel,GuardianNotificationPolicy(True))).status is DeliveryStatus.DELIVERED
    channel.deliver.assert_called_once()


def test_error_and_invalid_payload_skip_or_fail():
    channel = Mock()
    notifier = GuardianNotifier(channel,GuardianNotificationPolicy(True))
    assert deliver_cycle(None,notifier).reason == 'not_assessed'
    assert deliver_cycle(replace(cycle(),status=GuardianCycleStatus.ERROR),notifier).reason == 'not_assessed'
    assert deliver_cycle(replace(cycle(),assessment=None),notifier).reason == 'invalid_payload'
    assert notifier.notify(None).reason == 'invalid_payload'
    channel.deliver.assert_not_called()

@pytest.mark.parametrize('kind', [MacOSChannel,WindowsChannel])
def test_unsupported_platform(kind):
    process=Mock()
    assert kind(platform='linux',process=process).deliver('a','b').reason == 'unsupported_platform'
    process.assert_not_called()

@pytest.mark.skipif(sys.platform != 'darwin',reason='native macOS AppleScript compile')
def test_macos_native_compile_without_notification(tmp_path):
    from astropilot.local_notification import _SCRIPT
    target=tmp_path/'Guardian é.scpt'
    result=subprocess.run(['/usr/bin/osacompile','-o',str(target),'-'],input=_SCRIPT,
        encoding='utf-8',shell=False,timeout=5,capture_output=True,check=False)
    assert result.returncode == 0
    assert target.is_file()

@pytest.mark.parametrize('kind', [MacOSChannel, WindowsChannel])
@pytest.mark.parametrize('title,message', [(None,'message'),('title',None),('title','NUL\x00secret')])
def test_local_invalid_text(kind,title,message):
    process=Mock()
    assert kind(platform='darwin' if kind is MacOSChannel else 'win32',process=process).deliver(title,message).reason == 'invalid_payload'
    process.assert_not_called()


def test_windows_native_capacity_and_root_validation():
    import json
    process=Mock(return_value=SimpleNamespace(returncode=0))
    channel=WindowsChannel(platform='win32',process=process,system_root=r'C:\Windows')
    assert channel.deliver('🪐'*80,'☄🪐'*200).status is DeliveryStatus.DELIVERED
    title,message=json.loads(process.call_args.kwargs['input'])
    assert len(title.encode('utf-16-le')) <= 126
    assert len(message.encode('utf-16-le')) <= 510
    process.reset_mock()
    for root in ('relative',r'\\network\share',None):
        invalid=WindowsChannel(platform='win32',process=process,system_root=root)
        if root is None: invalid.system_root=None
        assert invalid.deliver('title','message').reason == 'process_failed'
    process.assert_not_called()
