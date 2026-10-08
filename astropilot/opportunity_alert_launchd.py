"""Generate an opt-in macOS LaunchAgent; never install or start a service."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import sys

from astropilot.opportunity_alert_host import load_config

LABEL = 'com.astropilot.opportunity-alert-host'


def _absolute(value):
    path = Path(value)
    if not path.is_absolute() or '\0' in str(path):
        raise ValueError('absolute_path_required')
    return path


def build_launch_agent(*, python, config, data_dir, log_dir, state_dir=None,
                       throttle_seconds=60):
    """Return a native process-only contract after validating deployment inputs."""
    if type(throttle_seconds) is not int or not 30 <= throttle_seconds <= 3600:
        raise ValueError('throttle_seconds_must_be_30_to_3600')
    # Resolving a venv's interpreter symlink can select the base environment.
    python = _absolute(python)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError('executable_python_required')
    config = _absolute(config).resolve(strict=True)
    load_config(config)
    data_dir = _absolute(data_dir).resolve(strict=True)
    log_dir = _absolute(log_dir).resolve(strict=True)
    if not data_dir.is_dir() or not log_dir.is_dir() or data_dir == log_dir:
        raise ValueError('distinct_existing_data_and_log_directories_required')
    stdout = log_dir / 'opportunity-alert-host.stdout.log'
    stderr = log_dir / 'opportunity-alert-host.stderr.log'
    destinations = [stdout.resolve(), stderr.resolve()]
    if len(set(destinations)) != 2 or config in destinations:
        raise ValueError('log_path_collision')
    for path in (stdout, stderr):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('regular_log_files_required')
        if path.exists() and os.path.samefile(path, config):
            raise ValueError('log_path_collision')
    if stdout.exists() and stderr.exists() and os.path.samefile(stdout, stderr):
        raise ValueError('log_path_collision')
    command = [str(python), '-u', '-m', 'astropilot.opportunity_alert_host',
               '--config', str(config), '--data-dir', str(data_dir)]
    if state_dir is not None:
        state_dir = _absolute(state_dir).resolve()
        if state_dir in (config, log_dir) or (state_dir.exists() and not state_dir.is_dir()):
            raise ValueError('invalid_state_directory')
        command.extend(['--state-dir', str(state_dir)])
    return {
        'Label': LABEL,
        'ProgramArguments': command,
        'RunAtLoad': True,
        'KeepAlive': {'SuccessfulExit': False},
        'ThrottleInterval': throttle_seconds,
        'ExitTimeOut': 120,
        'StandardOutPath': str(stdout),
        'StandardErrorPath': str(stderr),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Print an Opportunity Alerts macOS LaunchAgent; no installation.')
    for name in ('python', 'config', 'data-dir', 'log-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--throttle-seconds', type=int, default=60)
    args = parser.parse_args(argv)
    try:
        job = build_launch_agent(**vars(args))
    except (ValueError, OSError):
        print('invalid_opportunity_alert_launchd_configuration', file=sys.stderr)
        return 2
    sys.stdout.write(plistlib.dumps(job, sort_keys=True).decode('utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
