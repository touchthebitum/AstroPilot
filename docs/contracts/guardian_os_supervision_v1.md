# Guardian OS supervision/autostart v1

Contract written before implementation. Process supervision only; Guardian
UNKNOWN, recommendation-only, evidence, watermark and host lock semantics stay
unchanged. No notifications, hardware actions, UI/API, Field Lab or NAS changes.

## Deployment and restart

Opt-in generators only: no install/start calls. Absolute existing interpreter,
config, data and distinct log directory; optional absolute state directory.
Preserve interpreter symlinks for virtual environments. Validate Guardian config
before generation AND before supervisor launch; invalid configuration fails
fast with exit 2, without launching host or consuming retries. No cwd reliance,
shell, environment expansion, dynamic command templates or executable providers.
Generator output must be reviewed against the installed Python environment.

Both OSes invoke `astropilot.guardian_os_supervisor`, which starts only the
existing Guardian host CLI through a gated child entry. The application owns
ALL retries: default three total launches including initial, 60 seconds between
failures; count 1..10, delay 60..3600 seconds. Exit 0 stops; nonzero/crash/spawn
failure consumes budget; exhaustion exits nonzero (crash statuses normalized).
No budget reset after successful uptime. New explicit OS invocation/logon starts
a new budget. Runtime configuration is revalidated before each child: invalid
config fails immediately. No retry of domain cycles or risk decisions.

macOS: unique fixed label `com.astropilot.guardian-host`, RunAtLoad, KeepAlive
false (including exhaustion), ExitTimeOut 120, AbandonProcessGroup false. launchd
provides logon startup and process group cleanup; it does not restart supervisor
crashes. Application handles host failures. One label per user login domain.
Windows: disabled-by-default Task Scheduler XML, explicit LogonTrigger user and
InteractiveToken/LeastPrivilege, IgnoreNew, ExecutionTimeLimit PT0S, no
RestartOnFailure, boot trigger, network/idle/battery gating or wake. Fixed
operator task name `AstroPilot Guardian`. #341 field trials showed native
RestartOnFailure did not replace the host; application owns resilience.

Supervisor lock `.guardian_os_supervisor.lock` spans retry waits; unchanged
`.guardian_host.lock` prevents duplicate hosts including direct manual launches.
Locks belong to data-dir; never remove/reset them to defeat ownership. The
supervisor's lock cannot replace the host lock. Alias configurations still hit
the resolved data-dir lock. Supervisor calls host entry only; no service/runner.

## Stop and containment

SIGINT/SIGTERM parent requests child SIGTERM on POSIX, CTRL_BREAK on Windows,
translated to the existing host SIGTERM handler. Wait 10 seconds, then kill and
reap within 10 seconds. Retry waits are interruptible; voluntary stop exits 0.
Windows uses the existing purely generic WindowsJob primitive from Opportunity
Alerts (no alert host/config/notification imports): non-inherited kill-on-close
job, assignment before stdin gate. Assignment failure never starts host; parent
death before assignment yields EOF. Hard parent death kills contained tree.
POSIX launchd owns process group cleanup with AbandonProcessGroup false; direct
foreground SIGKILL outside launchd cannot guarantee child cleanup. Use Ctrl+C or
SIGTERM for foreground stop. No portable claim that hard stop is graceful.
Windows Task Scheduler End is hard termination: job cleanup prevents orphan,
but shutdown event/cycle completion is not guaranteed. Console break in task
context is best effort. Disable autostart first, stop, verify both processes gone.

## Logs and operator acceptance

Append UTF-8 `guardian-host.stdout.log` and `guardian-host.stderr.log` contain
host events and supervisor diagnostics after stream setup. Fixed filenames,
regular distinct non-symlink files, no config hardlink collisions. LaunchAgent
also targets these paths. Errors before setup use stderr/OS task result. No
retention: rotate manually only while both processes are confirmed stopped.
Keep config, jobs, data and logs private to operator account.

macOS: generate with `python -m astropilot.guardian_launchd --python ABS
--config ABS --data-dir ABS --log-dir ABS > REVIEW.plist`. Inspect plist, copy
manually to ~/Library/LaunchAgents/com.astropilot.guardian-host.plist, then
`launchctl bootstrap gui/UID ABS_PLIST`. Stop/remove with `launchctl bootout
gui/UID ABS_PLIST`; confirm supervisor/child stopped before rotating/updating.
Exhausted job stays stopped; diagnose before explicit bootout/bootstrap.
Windows: generate with `python -m astropilot.guardian_windows_task --python ABS
--config ABS --data-dir ABS --log-dir ABS --user-id SID --output ABS_XML`.
Verify whoami /user, review XML, Register-ScheduledTask without Force under
`AstroPilot Guardian`, explicitly Enable-ScheduledTask then Start-ScheduledTask.
Disable-ScheduledTask then Stop-ScheduledTask before updates/removal.

Native acceptance after merge (operator-owned, CI installs nothing):
- installed wheel from unrelated cwd, spaces/Unicode deployment, real login;
- exactly one host, duplicate supervisor during run AND retry blocked;
- direct duplicate host blocked by lifetime lock;
- kill only host: delayed replacement; repeated crashes exhaust three launches;
- clean child exit 0: no restart; invalid config fails immediately;
- cooperative parent stop: child gone, shutdown event when signal available;
- OS hard stop: no remaining tree; record absent graceful shutdown events;
- logs append deterministically; stop then rotate; re-enable only after review;
- UNKNOWN/recommendation-only unchanged, no notifications/hardware/network
  in CI. Native CI validates XML only and uses isolated disabled/inert children.

Next after merge: Guardian notification channel v1, recommendation-only,
without hardware automation.

Primary native references: [Apple launchd plist manual](https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5),
[Microsoft Job Object limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information),
[Task Scheduler schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema).
Local macOS launchd.plist(5) confirms KeepAlive defaults to demand-only and
AbandonProcessGroup=false retains group cleanup. Native login/OS stop trials
remain operator acceptance, not claimed by generator or isolated CI tests.
