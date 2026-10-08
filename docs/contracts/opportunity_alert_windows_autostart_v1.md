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
restriction; no wake or missed-slot replay. Task Scheduler provides logon
autostart only. RestartOnFailure is removed: native trials on 2026-10-08 did not
restart the failed host. An application supervisor owns the restart budget:
at most 3 child launches in total, 60 seconds apart by default
(--restart-count 1..10; --restart-seconds 60..3600). Thus three consecutive
failures exhaust the default budget. Exit 0 stops supervision immediately;
nonzero exit, Windows crash status or spawn failure consumes the budget.
This does not retry alert delivery or business errors reported in cycles.
New logon/manual launches initiate a new budget; it is not a persistent global
budget. Exhaustion exits nonzero and requires operator diagnosis/restart.

Task Scheduler Exec cannot redirect streams. One direct Python action invokes
`-u -m astropilot.opportunity_alert_windows_supervisor --python ABS
--restart-count 3 --restart-seconds 60 --log-dir ABS --config ABS --data-dir ABS`
(optional --state-dir ABS). The supervisor launches a real child with the
explicit interpreter and absolute paths, without shell. A private --child
entry waits for a one-byte stdin gate, then invokes the unchanged stream adapter.
The adapter opens append-only UTF-8 host stdout/stderr and calls existing
host.main. Its optional --once forwards the existing single-cycle host mode
for isolated contract tests. No business or notification policy is changed.
Runtime supervisor validation deliberately does not read config: missing or
invalid config belongs to the child and returns adapter exit 2, eligible for
restart. XML generation still validates config before output.
Supervisor lifetime lock in data supplements IgnoreNew and the unchanged host
lifetime lock, including during retry waits. Locks release on process death.
Interpreter path remains unresolved to preserve venv selection. Inputs must be
absolute existing local deployment paths; config validated before XML output.
Windows argv quoting uses subprocess.list2cmdline; XML uses ElementTree escaping.
Generation can be tested cross-platform with native absolute fixture paths.
Deployment generation must run on Windows for Windows filesystem validation.
Logs must be distinct regular non-symlink files, separate from config and data;
no automatic retention. Failures opening logs exit nonzero before host launch.

Windows child containment uses an unnamed, non-inherited Job Object with
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE. Assignment must succeed before releasing
the stdin gate; failure terminates the gated child and never starts host work.
If parent dies before assignment, stdin EOF makes child exit without starting
the host. Once assigned, parent death closes the sole job handle and kills the
child/tree. No breakaway flag is requested. Incompatible enclosing job policy
fails closed; diagnose foreground rather than running an uncontained host.
On cooperative parent SIGINT/SIGTERM, request CTRL_BREAK_EVENT for the child
process group, translated to the existing host SIGTERM handler, wait up to
10 seconds, then kill/reap if necessary. Console control is best effort and may
be unavailable in Task Scheduler's interactive context.
AllowHardTerminate=true permits operator End, but TerminateProcess is not
POSIX SIGTERM: job cleanup prevents a persistent orphan, not a guarantee of a
shutdown event, completed cycle or delivery. Disable first, End, then confirm
both supervisor and child stopped before updates. Use foreground Ctrl+C when
graceful shutdown is required. Never delete/reset ledger, watermark or locks.
No scheduled task is installed in tests; native job tests use inert children.

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
before adapter setup and supervisor diagnostics have no dedicated log; inspect LastTaskResult/history and
verify the selected installed environment in foreground.
Liveness does not prove business readiness. Rotate only while confirmed stopped;
V1 logs grow without limit. Keep config/XML/logs private to the login user.

## Native field evidence: Windows 11, 2026-10-08

Interactive standard account Franck Testé, baseline PR #340:
XML generation/import and RestartOnFailure Count=3 Interval=PT1M present;
logon autostart, Running host, dedicated logs, lifetime lock and native Windows
notification passed. Rename config.json, trigger logon: child/adapter exits 2.
After more than 70 seconds Task Scheduler remains Ready, LastRunTime remains
15:08:29, LastTaskResult=2, and no new host process exists. Start-ScheduledTask
also did not restart. External forced kill returned 0xFFFFFFFF without restart.
This confirms that the configured native restart did not provide resilience in
this deployment; it does not establish the internal Windows failure cause or
a universal Task Scheduler defect. The corrective contract therefore removes
that dependency. Application supervision is the primary and only retry owner.

## Corrective native acceptance checklist after merge

Review/import disabled XML; enable and verify next logon starts exactly one host
from unrelated cwd. Check actual SID and interactive notification context.
Confirm XML action targets supervisor, explicit interpreter, Count=3/seconds=60
arguments and no RestartOnFailure. Preserve config backup, rename config.json,
start through logon, observe child exit 2 while supervisor stays Running.
Restore config before 60 seconds: a new child starts successfully without a new
task invocation; LastRunTime remains the supervisor's original launch time.
Repeat with Start-ScheduledTask. Leave config missing: initial plus two retries
then supervisor nonzero/Ready. Kill only the host: observe delayed replacement.
Clean child exit 0 does not restart. During Running and retry delay, duplicate
supervisor must exit without another host; direct duplicate host remains blocked.
Disable/End, verify both processes gone and no unwanted restart;
record forced-stop effects and any absent shutdown event. Check manual duplicate
fails without a cycle, Unicode/spaces paths, logs and rotation, installed wheel.
No notifications or real host launches in CI. No durable outbox in this scope.
After merge, use real trials to decide whether durable delivery retry is needed.

References: [schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema),
[restart](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-restartonfailure-settingstype-element),
[hard termination](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-allowhardterminate-settingstype-element).
