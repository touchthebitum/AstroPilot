"""Generated native contract plus real host behavior; never load a LaunchAgent."""
import ast
import inspect
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import time

import pytest
from astropilot.guardian_launchd import build_launch_agent, main


def inputs(tmp_path):
    config = tmp_path / 'config avec accents é.json'
    config.write_text(json.dumps(dict(schema_version=1, interval_seconds=3600,
                                     anchor='2026-01-01T00:00:00+00:00')))
    data, logs = tmp_path / 'data', tmp_path / 'logs'
    data.mkdir()
    logs.mkdir()
    return dict(python=Path(sys.executable), config=config, data_dir=data, log_dir=logs)


def test_absolute_command_and_native_restart_contract(tmp_path):
    args = inputs(tmp_path)
    job = build_launch_agent(**args)
    command = job['ProgramArguments']
    assert command[:4] == [str(args['python']), '-u', '-m', 'astropilot.guardian_os_supervisor']
    assert '--restart-count' in command and '--python' in command
    for key in ('config', 'data_dir', 'log_dir'):
        assert str(args[key].resolve()) in command
    assert job['Label'] == 'com.astropilot.guardian-host'
    assert job['RunAtLoad'] is True
    # Application owns bounded retry; launchd never resets the budget.
    assert job['KeepAlive'] is False
    assert job['AbandonProcessGroup'] is False
    assert job['ThrottleInterval'] == 60
    assert job['ExitTimeOut'] == 120
    assert 'StartInterval' not in job and 'StartCalendarInterval' not in job
    assert 'WorkingDirectory' not in job and 'EnvironmentVariables' not in job
    assert job['StandardOutPath'] == str(args['log_dir'] / 'guardian-host.stdout.log')
    assert job['StandardErrorPath'] == str(args['log_dir'] / 'guardian-host.stderr.log')
    assert plistlib.loads(plistlib.dumps(job)) == job


@pytest.mark.parametrize('delay', [True, 0, 59, 3601, 1.5])
def test_backoff_bounds(tmp_path, delay):
    with pytest.raises(ValueError):
        build_launch_agent(**inputs(tmp_path), restart_seconds=delay)


@pytest.mark.parametrize('delay', [60, 3600])
def test_backoff_endpoints_and_state(tmp_path, delay):
    state = tmp_path / 'state'
    job = build_launch_agent(**inputs(tmp_path), restart_seconds=delay, state_dir=state)
    assert str(delay) in job['ProgramArguments']
    assert job['ProgramArguments'][-2:] == ['--state-dir', str(state)]
    assert not state.exists()


@pytest.mark.parametrize('key', ['python', 'config', 'data_dir', 'log_dir', 'state_dir'])
def test_relative_paths_rejected(tmp_path, key):
    args = inputs(tmp_path)
    args[key] = Path('relative')
    with pytest.raises(ValueError):
        build_launch_agent(**args)


def test_invalid_inputs_fail_before_output(tmp_path, capsys):
    args = inputs(tmp_path)
    args['config'].write_text('{}')
    assert main(['--python', str(args['python']), '--config', str(args['config']),
        '--data-dir', str(args['data_dir']), '--log-dir', str(args['log_dir'])]) == 2
    assert capsys.readouterr().out == ''
    args['config'].unlink()
    with pytest.raises((ValueError, OSError)):
        build_launch_agent(**args)


def test_missing_interpreter_and_directories(tmp_path):
    args = inputs(tmp_path)
    for key in ('python', 'data_dir', 'log_dir'):
        with pytest.raises((ValueError, OSError)):
            build_launch_agent(**(args | {key: tmp_path / 'missing'}))
    with pytest.raises(ValueError):
        build_launch_agent(**(args | {'python': args['config']}))


def test_log_alias_does_not_overwrite_config(tmp_path):
    args = inputs(tmp_path)
    (args['log_dir'] / 'guardian-host.stdout.log').symlink_to(args['config'])
    with pytest.raises(ValueError):
        build_launch_agent(**args)
    with pytest.raises(ValueError):
        build_launch_agent(**(args | {'log_dir': args['data_dir']}))


def test_cli_xml_and_no_side_effects(tmp_path, capsys):
    args = inputs(tmp_path)
    before = set(tmp_path.rglob('*'))
    assert main(['--python', str(args['python']), '--config', str(args['config']),
        '--data-dir', str(args['data_dir']), '--log-dir', str(args['log_dir'])]) == 0
    assert plistlib.loads(capsys.readouterr().out.encode()) == build_launch_agent(**args)
    assert set(tmp_path.rglob('*')) == before


def test_dependency_boundary():
    import astropilot.guardian_os_supervisor as module
    source = inspect.getsource(module)
    assert 'GuardianService' not in source and 'GuardianRunner' not in source
    assert 'decision.runners' not in source
    assert 'shell=True' not in source


def test_generated_disabled_process_from_other_cwd(tmp_path):
    args = inputs(tmp_path)
    job = build_launch_agent(**args)
    env = os.environ | {'PYTHONPATH': str(Path(__file__).resolve().parents[2])}
    result = subprocess.run(job['ProgramArguments'], cwd=tmp_path, env=env,
                            capture_output=True, timeout=20)
    assert result.returncode == 0
    log = Path(job['StandardOutPath']).read_text()
    assert '"event": "startup"' in log and '"event": "shutdown"' in log
    assert 'supervisor_child_exit' not in Path(job['StandardErrorPath']).read_text()


def test_venv_interpreter_symlink_is_preserved(tmp_path):
    args = inputs(tmp_path)
    interpreter = tmp_path / 'venv' / 'bin' / 'python'
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    assert build_launch_agent(**(args | {'python': interpreter}))['ProgramArguments'][0] == str(interpreter)


def test_hardlinked_log_config_rejected(tmp_path):
    args = inputs(tmp_path)
    os.link(args['config'], args['log_dir'] / 'guardian-host.stderr.log')
    with pytest.raises(ValueError):
        build_launch_agent(**args)


@pytest.mark.skipif(sys.platform != 'darwin', reason='native macOS plist lint only')
def test_native_plist_without_loading(tmp_path):
    path = tmp_path / 'review.plist'
    path.write_bytes(plistlib.dumps(build_launch_agent(**inputs(tmp_path))))
    result = subprocess.run(['/usr/bin/plutil', '-lint', str(path)],
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('count', [True, 0, 11, 1.5])
def test_restart_count_validation(tmp_path, count):
    with pytest.raises(ValueError):
        build_launch_agent(**inputs(tmp_path), restart_count=count)
