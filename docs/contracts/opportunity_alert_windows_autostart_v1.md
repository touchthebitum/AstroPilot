# Opportunity Alerts Windows autostart v1

Process supervision only. No host, notification, runner, scheduler, ledger,
Tonight, scoring, API, Field Lab or NAS changes. No installation by generator.

## Contract (written before implementation)

Generate reviewable Task Scheduler 1.2 XML, disabled by default. Explicit user
SID/name required and shared by LogonTrigger and InteractiveToken principal;
LeastPrivilege, current interactive user only, no boot/service/password mode.
Operator must verify identity matches their current account before import.
Enable explicitly after review. IgnoreNew supplements the unchanged host lock.
ExecutionTimeLimit PT0S removes the native 72-hour default. No battery/idle/network
restriction; no wake or missed-slot replay. RestartOnFailure: PT1M, Count 3 by
default, bounded 60..3600 seconds and 1..10 attempts. This is native task failure
restart, not retry of alert delivery or business errors reported in cycles.
Exit 0 does not request failure restart. New logon/manual launches can initiate
a new run; this is not a persistent global retry budget.

Task Scheduler Exec cannot redirect streams. One direct Python action invokes
`-u -m astropilot.opportunity_alert_windows_task_host --log-dir ABS --config ABS
--data-dir ABS` (optional --state-dir ABS). The minimal adapter opens append-only
UTF-8 stdout/stderr logs and calls existing host.main in the same process. No
shell, subprocess, dynamic script, child supervision, or business dependency.
Interpreter path remains unresolved to preserve venv selection. Inputs must be
absolute existing local deployment paths; config validated before XML output.
Windows argv quoting uses subprocess.list2cmdline; XML uses ElementTree escaping.
Generation can be tested cross-platform with native absolute fixture paths.
Deployment generation must run on Windows for Windows filesystem validation.
Logs must be distinct regular non-symlink files, separate from config and data;
no automatic retention. Failures opening logs exit nonzero before host launch.

AllowHardTerminate=true permits controlled operator End, but TerminateProcess
is not POSIX SIGTERM: no guaranteed shutdown event or completed active cycle.
Do not promise graceful Task Scheduler stop. Disable first, then End and confirm
stopped before config/log rotation/update/restart; lifetime lock releases on death.
Use foreground Ctrl+C when a graceful shutdown is required. Never delete/reset
ledger, watermark or lock to restart. No scheduled task is installed in tests.

## Operator procedure (PowerShell; paths are examples)

Use installed Python with AstroPilot, existing config/data and dedicated local
owner-only log folder. Confirm `whoami /user`; use its SID below. Check installed
module with the selected interpreter. From any cwd:

```powershell
& 'C:\Alert Env\Scripts\python.exe' -m astropilot.opportunity_alert_windows_task --python 'C:\Alert Env\Scripts\python.exe' --config 'C:\Alerts\config.json' --data-dir 'C:\Alerts\data' --log-dir 'C:\Alerts\logs' --user-id 'S-1-5-21-REPLACE' --output 'C:\Alerts\review.xml'
# Check LASTEXITCODE, inspect XML paths, identity, disabled state and policy.
Register-ScheduledTask -TaskName 'AstroPilot Opportunity Alerts' -Xml (Get-Content -Raw -LiteralPath 'C:\Alerts\review.xml')
Enable-ScheduledTask -TaskName 'AstroPilot Opportunity Alerts'
Start-ScheduledTask -TaskName 'AstroPilot Opportunity Alerts'
Get-ScheduledTaskInfo -TaskName 'AstroPilot Opportunity Alerts'
Disable-ScheduledTask -TaskName 'AstroPilot Opportunity Alerts'
Stop-ScheduledTask -TaskName 'AstroPilot Opportunity Alerts'
# Confirm stopped before updates. Enable/start again only after review.
# Unregister-ScheduledTask removes persistent autostart after stopping.
```

No Force: do not overwrite existing tasks. Next user logon starts enabled task.
Diagnostics: task state/LastTaskResult/history plus dedicated
opportunity-alert-host.stdout.log (JSON events), stderr.log (diagnostics after stream setup). Interpreter/module import failures
before adapter setup have no dedicated log; inspect LastTaskResult/history and
verify the selected installed environment in foreground.
Liveness does not prove business readiness. Rotate only while confirmed stopped;
V1 logs grow without limit. Keep config/XML/logs private to the login user.

## Native acceptance pending: Windows 11

Review/import disabled XML; enable and verify next logon starts exactly one host
from unrelated cwd. Check actual SID and interactive notification context.
Crash isolated host and observe bounded failure restart/delay/exhaustion; clean
exit does not restart. Disable/End, verify process gone and no unwanted restart;
record forced-stop effects and any absent shutdown event. Check manual duplicate
fails without a cycle, Unicode/spaces paths, logs and rotation, installed wheel.
No notifications or real host launches in CI. No durable outbox in this scope.
After merge, use real trials to decide whether durable delivery retry is needed.

References: [schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema),
[restart](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-restartonfailure-settingstype-element),
[hard termination](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-allowhardterminate-settingstype-element).
