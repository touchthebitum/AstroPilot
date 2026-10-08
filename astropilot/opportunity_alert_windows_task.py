"""Generate disabled, reviewable user-logon Task Scheduler XML; never install."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from astropilot.opportunity_alert_launchd import build_launch_agent

NAMESPACE = 'http://schemas.microsoft.com/windows/2004/02/mit/task'


def build_task(*, python, config, data_dir, log_dir, user_id, state_dir=None,
               restart_seconds=60, restart_count=3):
    if (not isinstance(user_id, str) or not user_id.strip()
            or any(ord(c) < 32 for c in user_id)):
        raise ValueError('explicit_user_identity_required')
    if type(restart_seconds) is not int or not 60 <= restart_seconds <= 3600:
        raise ValueError('invalid_restart_interval')
    if type(restart_count) is not int or not 1 <= restart_count <= 10:
        raise ValueError('invalid_restart_count')
    if os.name == 'nt':
        for path in (python, config, data_dir, log_dir, state_dir):
            if path is not None and str(path).startswith(('\\\\', '//')):
                raise ValueError('local_deployment_paths_required')
    # Reuse existing deployment validation only; no launchd installation occurs.
    deployment = build_launch_agent(python=python, config=config, data_dir=data_dir,
                                   log_dir=log_dir, state_dir=state_dir)
    host_args = deployment['ProgramArguments'][4:]
    args = ['-u', '-m', 'astropilot.opportunity_alert_windows_supervisor',
            '--python', str(python), '--restart-seconds', str(restart_seconds),
            '--restart-count', str(restart_count),
            '--log-dir', str(Path(log_dir).resolve()), *host_args]
    for value in [str(python), *args]:
        if any(ord(c) < 32 for c in value) or '%' in value:
            raise ValueError('unsupported_task_path')
    root = ET.Element('Task', {'xmlns': NAMESPACE, 'version': '1.2'})
    def add(parent, name, text=None, **attrs):
        node = ET.SubElement(parent, name, attrs)
        if text is not None:
            node.text = str(text)
        return node
    registration = add(root, 'RegistrationInfo')
    add(registration, 'Description', 'Opt-in Opportunity Alerts user host; review before enabling.')
    trigger = add(add(root, 'Triggers'), 'LogonTrigger')
    add(trigger, 'Enabled', 'true')
    add(trigger, 'UserId', user_id)
    principal = add(add(root, 'Principals'), 'Principal', id='AlertUser')
    add(principal, 'UserId', user_id)
    add(principal, 'LogonType', 'InteractiveToken')
    add(principal, 'RunLevel', 'LeastPrivilege')
    settings = add(root, 'Settings')
    for name, value in {'MultipleInstancesPolicy': 'IgnoreNew',
                        'DisallowStartIfOnBatteries': 'false', 'StopIfGoingOnBatteries': 'false',
                        'AllowHardTerminate': 'true', 'StartWhenAvailable': 'false',
                        'RunOnlyIfNetworkAvailable': 'false', 'AllowStartOnDemand': 'true',
                        'Enabled': 'false', 'Hidden': 'false', 'RunOnlyIfIdle': 'false',
                        'WakeToRun': 'false', 'ExecutionTimeLimit': 'PT0S'}.items():
        add(settings, name, value)
    action = add(add(root, 'Actions', Context='AlertUser'), 'Exec')
    add(action, 'Command', deployment['ProgramArguments'][0])
    add(action, 'Arguments', subprocess.list2cmdline(args))
    ET.indent(root)
    # No encoding declaration: UTF-8 files and COM UTF-16 BSTR both accept it.
    return ET.tostring(root, encoding='unicode', xml_declaration=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('python', 'config', 'data-dir', 'log-dir', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--restart-seconds', type=int, default=60)
    parser.add_argument('--restart-count', type=int, default=3)
    args = vars(parser.parse_args(argv))
    output = args.pop('output')
    try:
        xml = build_task(**args)
        if not output.is_absolute():
            raise ValueError('absolute_output_required')
        # Never overwrite any existing deployment/config/log file.
        with output.open('x', encoding='utf-8') as handle:
            handle.write(xml)
    except (ValueError, OSError):
        print('invalid_opportunity_alert_windows_task_configuration', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
