"""Bounded process supervision for the opt-in Windows user-logon alert host."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event

# Set only while main runs; retry waits remain interruptible.
def retry_wait(seconds):
    return _stop.wait(seconds)


_stop = Event()


def stop_child(child):
    if child.poll() is not None:
        return
    try:
        child.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGTERM)
        child.wait(timeout=10)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    child.kill()
    child.wait(timeout=10)


def supervise(launch, stop, *, restart_count=3, restart_seconds=60, wait=None):
    """At most restart_count child launches, including the initial attempt."""
    wait = wait or stop.wait
    for attempt in range(restart_count):
        if stop.is_set():
            return 0
        child = None
        try:
            child = launch()
            while not stop.is_set():
                try:
                    code = child.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            else:
                stop_child(child)
                return 0
        except OSError:
            if child is not None:
                stop_child(child)
            code = 2
        except BaseException:
            if child is not None:
                stop_child(child)
            raise
        if code == 0 or stop.is_set():
            return 0
        print(f'opportunity_alert_supervisor_child_exit={code} attempt={attempt}', file=sys.stderr, flush=True)
        if attempt == restart_count - 1:
            print('opportunity_alert_supervisor_exhausted', file=sys.stderr, flush=True)
            # Windows crash statuses can exceed the signed exit-code range.
            return code if 1 <= code <= 255 else 1
        if wait(restart_seconds):
            return 0
    raise AssertionError('unreachable')


def launch_child(command, job):
    child = subprocess.Popen(command, stdin=subprocess.PIPE, shell=False, close_fds=True,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
    try:
        if job is not None:
            job.assign(child)
        # Child cannot enter adapter/host until containment succeeds. If parent
        # dies before assignment, EOF makes the waiting child exit without a host.
        child.stdin.write(b'1')
        child.stdin.close()
        return child
    except BaseException:
        try:
            child.stdin.close()
        finally:
            stop_child(child)
        raise


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == '--child':
        if sys.stdin.buffer.read(1) != b'1':
            return 2
        # Existing adapter preserves exit semantics and dedicated UTF-8 logs.
        from astropilot.opportunity_alert_windows_task_host import main as host_main
        if os.name == 'nt':
            # Existing host handles SIGTERM. Translate the cooperative console
            # break without changing its business or notification behavior.
            signal.signal(signal.SIGBREAK, lambda *_: signal.raise_signal(signal.SIGTERM))
        return host_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('python', 'config', 'data-dir', 'log-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--restart-seconds', type=int, default=60)
    parser.add_argument('--restart-count', type=int, default=3)
    args = parser.parse_args(argv)
    from astropilot.opportunity_alert_host import HostAlreadyRunning, host_lock, shutdown_signals
    try:
        if not 60 <= args.restart_seconds <= 3600 or not 1 <= args.restart_count <= 10:
            raise ValueError('invalid_restart_policy')
        # Config must be absolute, but need not exist yet: missing/invalid config
        # is a child failure eligible for restart, as in the native field trial.
        paths = (args.python, args.config, args.data_dir, args.log_dir, args.state_dir)
        if any(p is not None and (not p.is_absolute() or '\0' in str(p)) for p in paths):
            raise ValueError('absolute_paths_required')
        if not args.python.is_file() or not args.data_dir.is_dir() or not args.log_dir.is_dir():
            raise ValueError('existing_deployment_required')
        if args.data_dir.resolve() == args.log_dir.resolve():
            raise ValueError('distinct_data_and_log_directories_required')
        command = [str(args.python), '-u', '-m',
                   'astropilot.opportunity_alert_windows_supervisor', '--child',
                   '--log-dir', str(args.log_dir), '--config', str(args.config),
                   '--data-dir', str(args.data_dir)]
        if args.state_dir is not None:
            command += ['--state-dir', str(args.state_dir)]
        _stop.clear()
        with host_lock(args.data_dir / '.opportunity_alert_windows_supervisor.lock'):
            with shutdown_signals(_stop):
                if os.name == 'nt':
                    from astropilot.opportunity_alert_windows_job import WindowsJob
                    job_context = WindowsJob()
                else:
                    job_context = nullcontext(None)  # portable contract tests
                with job_context as job:
                    return supervise(lambda: launch_child(command, job), _stop,
                                     restart_count=args.restart_count,
                                     restart_seconds=args.restart_seconds, wait=retry_wait)
    except HostAlreadyRunning:
        print('opportunity_alert_windows_supervisor_already_running', file=sys.stderr)
        return 1
    except (ValueError, OSError):
        print('invalid_opportunity_alert_windows_supervisor_configuration', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
