"""Generate an opt-in macOS LaunchAgent; never install or start a service."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import sys

from astropilot.guardian_host import load_config

LABEL = 'com.astropilot.guardian-host'


def _absolute(value):
    path = Path(value)
    if (not path.is_absolute() or any(ord(c) < 32 for c in str(path))
            or '%' in str(path)):
        raise ValueError('absolute_path_required')
    return path


def build_launch_agent(*, python, config, data_dir, log_dir, state_dir=None,
                       restart_seconds=60, restart_count=3):
    """Return a native process-only contract after validating deployment inputs."""
    if type(restart_seconds) is not int or not 60 <= restart_seconds <= 3600:
        raise ValueError('invalid_restart_seconds')
    if type(restart_count) is not int or not 1 <= restart_count <= 10:
        raise ValueError('invalid_restart_count')
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
    stdout = log_dir / 'guardian-host.stdout.log'
    stderr = log_dir / 'guardian-host.stderr.log'
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
    command = [str(python), '-u', '-m', 'astropilot.guardian_os_supervisor',
               '--python', str(python), '--restart-count', str(restart_count),
               '--restart-seconds', str(restart_seconds), '--log-dir', str(log_dir),
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
        'KeepAlive': False,
        'AbandonProcessGroup': False,
        'ThrottleInterval': 60,
        'ExitTimeOut': 120,
        'StandardOutPath': str(stdout),
        'StandardErrorPath': str(stderr),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Print a Guardian macOS LaunchAgent; no installation.')
    for name in ('python', 'config', 'data-dir', 'log-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--restart-seconds', type=int, default=60)
    parser.add_argument('--restart-count', type=int, default=3)
    args = parser.parse_args(argv)
    try:
        job = build_launch_agent(**vars(args))
    except (ValueError, OSError):
        print('invalid_guardian_launchd_configuration', file=sys.stderr)
        return 2
    sys.stdout.write(plistlib.dumps(job, sort_keys=True).decode('utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
