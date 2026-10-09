"""Same-process stream adapter for the supervised Guardian host CLI."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys

from astropilot.guardian_host import main as host_main
from astropilot.guardian_launchd import build_launch_agent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('log-dir', 'config', 'data-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--once', action='store_true', help='Run the existing host for one cycle')
    args = parser.parse_args(argv)
    try:
        job = build_launch_agent(python=sys.executable, config=args.config,
                                data_dir=args.data_dir, log_dir=args.log_dir,
                                state_dir=args.state_dir)
        # Open both streams before starting host; preserve existing append history.
        with open(job['StandardOutPath'], 'a', encoding='utf-8', buffering=1) as stdout, \
             open(job['StandardErrorPath'], 'a', encoding='utf-8', buffering=1) as stderr:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                return host_main(['--config', str(args.config), '--data-dir', str(args.data_dir)]
                    + (['--state-dir', str(args.state_dir)] if args.state_dir else [])
                    + (['--once'] if args.once else []))
    except (ValueError, OSError):
        print('invalid_guardian_task_host_configuration', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
