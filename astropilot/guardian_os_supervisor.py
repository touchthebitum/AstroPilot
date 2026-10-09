"""Bounded process supervision for the opt-in Guardian host on macOS/Windows."""
from __future__ import annotations

import argparse
from contextlib import nullcontext, redirect_stdout, redirect_stderr
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
        print(f'guardian_supervisor_child_exit={code} attempt={attempt}', file=sys.stderr, flush=True)
        if attempt == restart_count - 1:
            print('guardian_supervisor_exhausted', file=sys.stderr, flush=True)
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
        # Stream adapter preserves existing host exit semantics and UTF-8 logs.
        from astropilot.guardian_task_host import main as host_main
        if os.name == 'nt':
            # Existing host handles SIGTERM. Translate the cooperative console
            # break without changing its Guardian behavior.
            signal.signal(signal.SIGBREAK, lambda *_: signal.raise_signal(signal.SIGTERM))
        return host_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('python', 'config', 'data-dir', 'log-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--restart-seconds', type=int, default=60)
    parser.add_argument('--restart-count', type=int, default=3)
    args = parser.parse_args(argv)
    from astropilot.guardian_host import HostAlreadyRunning, host_lock, shutdown_signals
    try:
        if not 60 <= args.restart_seconds <= 3600 or not 1 <= args.restart_count <= 10:
            raise ValueError('invalid_restart_policy')
        from astropilot.guardian_launchd import build_launch_agent
        deployment = build_launch_agent(python=args.python, config=args.config,
            data_dir=args.data_dir, log_dir=args.log_dir, state_dir=args.state_dir,
            restart_count=args.restart_count, restart_seconds=args.restart_seconds)
        if os.name == 'nt' and any(p is not None and str(p).startswith(('\\\\', '//'))
                for p in (args.python, args.config, args.data_dir, args.log_dir, args.state_dir)):
            raise ValueError('local_deployment_paths_required')
        command = [str(args.python), '-u', '-m',
                   'astropilot.guardian_os_supervisor', '--child',
                   '--log-dir', str(args.log_dir), '--config', str(args.config),
                   '--data-dir', str(args.data_dir)]
        if args.state_dir is not None:
            command += ['--state-dir', str(args.state_dir)]
        _stop.clear()
        with host_lock(args.data_dir / '.guardian_os_supervisor.lock'):
            with open(deployment['StandardOutPath'], 'a', encoding='utf-8', buffering=1) as stdout, \
                 open(deployment['StandardErrorPath'], 'a', encoding='utf-8', buffering=1) as stderr:
                with redirect_stdout(stdout), redirect_stderr(stderr), shutdown_signals(_stop):
                    if os.name == 'nt':
                        from astropilot.opportunity_alert_windows_job import WindowsJob
                        job_context = WindowsJob()
                    else:
                        job_context = nullcontext(None)
                    with job_context as job:
                        def launch():
                            # Config/path/log changes fail before any new host launch.
                            try:
                                build_launch_agent(python=args.python, config=args.config,
                                    data_dir=args.data_dir, log_dir=args.log_dir,
                                    state_dir=args.state_dir)
                            except OSError as error:
                                # Deployment failure is fail-fast, not a spawn failure.
                                raise ValueError('deployment_invalid') from error
                            return launch_child(command, job)
                        return supervise(launch, _stop, restart_count=args.restart_count,
                            restart_seconds=args.restart_seconds, wait=retry_wait)
    except HostAlreadyRunning:
        print('guardian_os_supervisor_already_running', file=sys.stderr)
        return 1
    except (ValueError, OSError):
        print('invalid_guardian_os_supervisor_configuration', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
