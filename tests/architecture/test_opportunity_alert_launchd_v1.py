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
from astropilot.opportunity_alert_launchd import build_launch_agent, main


def inputs(tmp_path):
    config = tmp_path / 'config avec accents é.json'
    config.write_text(json.dumps(dict(schema_version=1, interval_seconds=3600,
                                     policy={}, availability=None)))
    data, logs = tmp_path / 'data', tmp_path / 'logs'
    data.mkdir()
    logs.mkdir()
    return dict(python=Path(sys.executable), config=config, data_dir=data, log_dir=logs)


def test_absolute_command_and_native_restart_contract(tmp_path):
    args = inputs(tmp_path)
    job = build_launch_agent(**args)
    command = job['ProgramArguments']
    assert command == [str(args['python'].absolute()), '-u', '-m',
        'astropilot.opportunity_alert_host', '--config', str(args['config'].resolve()),
        '--data-dir', str(args['data_dir'].resolve())]
    assert job['Label'] == 'com.astropilot.opportunity-alert-host'
    assert job['RunAtLoad'] is True
    # Nonzero/crash retries; graceful 0 stays stopped. No OR conditions.
    assert job['KeepAlive'] == {'SuccessfulExit': False}
    assert job['ThrottleInterval'] == 60
    assert job['ExitTimeOut'] == 120
    assert 'StartInterval' not in job and 'StartCalendarInterval' not in job
    assert 'WorkingDirectory' not in job and 'EnvironmentVariables' not in job
    assert job['StandardOutPath'] == str(args['log_dir'] / 'opportunity-alert-host.stdout.log')
    assert job['StandardErrorPath'] == str(args['log_dir'] / 'opportunity-alert-host.stderr.log')
    assert plistlib.loads(plistlib.dumps(job)) == job


@pytest.mark.parametrize('delay', [True, 0, 29, 3601, 1.5])
def test_backoff_bounds(tmp_path, delay):
    with pytest.raises(ValueError):
        build_launch_agent(**inputs(tmp_path), throttle_seconds=delay)


@pytest.mark.parametrize('delay', [30, 3600])
def test_backoff_endpoints_and_state(tmp_path, delay):
    state = tmp_path / 'state'
    job = build_launch_agent(**inputs(tmp_path), throttle_seconds=delay, state_dir=state)
    assert job['ThrottleInterval'] == delay
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
    (args['log_dir'] / 'opportunity-alert-host.stdout.log').symlink_to(args['config'])
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
    import astropilot.opportunity_alert_launchd as module
    tree = ast.parse(inspect.getsource(module))
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports == {'__future__', 'pathlib', 'astropilot.opportunity_alert_host'}
    assert {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} <= {
        'argparse', 'os', 'plistlib', 'sys'}
    host_imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                    and n.module == 'astropilot.opportunity_alert_host' for a in n.names}
    assert host_imports == {'load_config'}


def wait_start(path, process):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if path.exists() and '"event": "startup"' in path.read_text():
            return
        assert process.poll() is None, 'host exited before startup'
        time.sleep(.05)
    pytest.fail('host startup timed out')


@pytest.mark.skipif(os.name == 'nt', reason='native POSIX signal smoke')
def test_generated_process_logs_duplicate_crash_restart_and_sigterm(tmp_path):
    args = inputs(tmp_path)
    job = build_launch_agent(**args)
    # Test from an unrelated cwd with explicit source import path; deployment
    # instead uses the installed wheel (no PYTHONPATH in the generated plist).
    env = os.environ | {'PYTHONPATH': str(Path(__file__).resolve().parents[2])}
    out = Path(job['StandardOutPath'])
    err = Path(job['StandardErrorPath'])
    with out.open('ab') as stdout, err.open('ab') as stderr:
        process = subprocess.Popen(job['ProgramArguments'], cwd=tmp_path,
                                   env=env, stdout=stdout, stderr=stderr)
        try:
            wait_start(out, process)
            duplicate = subprocess.run(job['ProgramArguments'] + ['--once'], cwd=tmp_path,
                env=env, capture_output=True, text=True, timeout=15)
            assert duplicate.returncode == 1
            assert 'already_running' in duplicate.stdout
            process.kill()  # crash releases lifetime lock without Python cleanup
            assert process.wait(timeout=15) != 0
            with out.open('wb'):
                pass
            process = subprocess.Popen(job['ProgramArguments'], cwd=tmp_path,
                                       env=env, stdout=stdout, stderr=stderr)
            wait_start(out, process)
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=15) == 0
            assert '"event": "shutdown"' in out.read_text()
            assert err.read_text() == ''
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=15)


def test_venv_interpreter_symlink_is_preserved(tmp_path):
    args = inputs(tmp_path)
    interpreter = tmp_path / 'venv' / 'bin' / 'python'
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    assert build_launch_agent(**(args | {'python': interpreter}))['ProgramArguments'][0] == str(interpreter)


def test_hardlinked_log_config_rejected(tmp_path):
    args = inputs(tmp_path)
    os.link(args['config'], args['log_dir'] / 'opportunity-alert-host.stderr.log')
    with pytest.raises(ValueError):
        build_launch_agent(**args)
