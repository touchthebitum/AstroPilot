import json
import sys
import xml.etree.ElementTree as ET

import pytest

from astropilot.opportunity_alert_windows_task import build_task

NS = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}

@pytest.fixture
def deployment(tmp_path):
    root = tmp_path / 'Espaces été & 汉字'
    root.mkdir()
    config = root / 'config.json'
    config.write_text(json.dumps({'schema_version': 1, 'interval_seconds': 60,
                                 'policy': {}, 'availability': None}))
    data = root / 'data'
    logs = root / 'logs'
    data.mkdir()
    logs.mkdir()
    return dict(python=sys.executable, config=config, data_dir=data,
                log_dir=logs, user_id='S-1-5-21-123')


def test_definition(deployment):
    xml = build_task(**deployment)
    assert not xml.startswith('<?xml')  # COM BSTR must not claim UTF-8 bytes.
    root = ET.fromstring(xml)
    def value(path):
        return root.find(path, NS).text
    assert value('t:Triggers/t:LogonTrigger/t:UserId') == deployment['user_id']
    assert value('t:Principals/t:Principal/t:LogonType') == 'InteractiveToken'
    assert value('t:Principals/t:Principal/t:UserId') == deployment['user_id']
    for name, expected in {'Enabled': 'false', 'MultipleInstancesPolicy': 'IgnoreNew',
                           'ExecutionTimeLimit': 'PT0S', 'AllowHardTerminate': 'true',
                           'DisallowStartIfOnBatteries': 'false',
                           'StopIfGoingOnBatteries': 'false'}.items():
        assert value('t:Settings/t:' + name) == expected
    assert value('t:Settings/t:RestartOnFailure/t:Count') == '3'
    assert value('t:Settings/t:RestartOnFailure/t:Interval') == 'PT60S'
    assert value('t:Actions/t:Exec/t:Command') == sys.executable
    args = value('t:Actions/t:Exec/t:Arguments')
    assert args.startswith('-u -m astropilot.opportunity_alert_windows_task_host ')
    for key in ('config', 'data_dir', 'log_dir'):
        assert '"' + str(deployment[key]) + '"' in args
    assert root.find('t:Triggers/t:BootTrigger', NS) is None


@pytest.mark.parametrize('key', ['python', 'config', 'data_dir', 'log_dir'])
def test_relative_rejected(deployment, key):
    deployment[key] = 'relative'
    with pytest.raises(ValueError):
        build_task(**deployment)


def test_invalid_config(deployment):
    deployment['config'].write_text('{}')
    with pytest.raises(ValueError):
        build_task(**deployment)


@pytest.mark.parametrize('key,value', [('restart_seconds', 59), ('restart_seconds', 3601),
                                      ('restart_count', 0), ('restart_count', 11),
                                      ('user_id', ''), ('user_id', 'x\ncode')])
def test_invalid_policy(deployment, key, value):
    with pytest.raises(ValueError):
        build_task(**deployment, **{key: value}) if key != 'user_id' else build_task(**(deployment | {key: value}))


def test_adapter_streams_and_exit(deployment, monkeypatch):
    from astropilot import opportunity_alert_windows_task_host as adapter
    def host(args):
        assert args == ['--config', str(deployment['config']), '--data-dir', str(deployment['data_dir'])]
        print('startup été')
        print('diagnostic', file=sys.stderr)
        return 7
    monkeypatch.setattr(adapter, 'host_main', host)
    assert adapter.main(['--log-dir', str(deployment['log_dir']), '--config', str(deployment['config']),
                         '--data-dir', str(deployment['data_dir'])]) == 7
    assert 'startup été' in (deployment['log_dir'] / 'opportunity-alert-host.stdout.log').read_text(encoding='utf-8')
    assert 'diagnostic' in (deployment['log_dir'] / 'opportunity-alert-host.stderr.log').read_text()


def test_no_shell_or_process_launch():
    import inspect
    from astropilot import opportunity_alert_windows_task as generator
    from astropilot import opportunity_alert_windows_task_host as adapter
    for module in (generator, adapter):
        source = inspect.getsource(module)
        assert 'shell=True' not in source
        assert 'Popen' not in source
        assert 'subprocess.run' not in source


def test_native_xml_validation_only(deployment):
    import os
    import subprocess
    if os.name != 'nt':
        pytest.skip('Native Task Scheduler validation requires Windows')
    # TASK_VALIDATE_ONLY=1: validate definition without registration or execution.
    script = "$ErrorActionPreference='Stop'; [Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false); $doc=[xml][Console]::In.ReadToEnd(); $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; $doc.SelectNodes('//*[local-name()=\"UserId\"]') | ForEach-Object { $_.InnerText=$sid }; $xml=$doc.OuterXml; $s=New-Object -ComObject Schedule.Service; $s.Connect(); $null=$s.GetFolder('\\').RegisterTask('AstroPilot-validation-only', $xml, 1, $null, $null, 3, $null)"
    powershell = os.path.join(os.environ['SystemRoot'], 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', script],
                            input=build_task(**deployment), text=True, encoding='utf-8',
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_adapter_duplicate_and_logs(deployment, tmp_path):
    import os
    import subprocess
    from astropilot.opportunity_alert_host import host_lock
    args = [sys.executable, '-u', '-m', 'astropilot.opportunity_alert_windows_task_host',
            '--log-dir', str(deployment['log_dir']), '--config', str(deployment['config']),
            '--data-dir', str(deployment['data_dir'])]
    env = dict(os.environ, PYTHONPATH=str(__import__('pathlib').Path(__file__).resolve().parents[2]))
    with host_lock(deployment['data_dir'] / '.opportunity_alert_host.lock'):
        result = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, timeout=20)
    assert result.returncode == 1
    log = (deployment['log_dir'] / 'opportunity-alert-host.stdout.log').read_text()
    assert 'opportunity_alert_host_already_running' in log
    assert '"event": "startup"' not in log
    assert '"event": "cycle"' not in log


def test_cli_no_overwrite(deployment, tmp_path):
    from astropilot.opportunity_alert_windows_task import main
    output = tmp_path / 'review.xml'
    args = [item for key, value in deployment.items() for item in ('--' + key.replace('_', '-'), str(value))]
    assert main(args + ['--output', str(output)]) == 0
    before = output.read_bytes()
    assert main(args + ['--output', str(output)]) == 2
    assert output.read_bytes() == before


def test_invalid_adapter_never_calls_host(deployment, monkeypatch):
    from astropilot import opportunity_alert_windows_task_host as adapter
    deployment['config'].write_text('{}')
    monkeypatch.setattr(adapter, 'host_main', lambda *_: pytest.fail('host started'))
    assert adapter.main(['--log-dir', str(deployment['log_dir']), '--config', str(deployment['config']),
                         '--data-dir', str(deployment['data_dir'])]) == 2


@pytest.mark.parametrize('key', ['config', 'data_dir', 'log_dir'])
def test_task_expansion_rejected(deployment, key):
    # Percent expansion is a native Task Scheduler hazard, not shell quoting.
    path = deployment[key]
    new = path.with_name('%environment%' + path.name)
    path.rename(new)
    deployment[key] = new
    with pytest.raises(ValueError):
        build_task(**deployment)
