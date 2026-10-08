# Opt-in Opportunity Alerts LaunchAgent (macOS)

This deployment starts at user login, not before login or while logged out.
Use an installed AstroPilot Python environment with the host module available;
the NightMerit GUI executable is not a substitute for Python. Windows 11 needs
its own reviewed autostart integration. No service is activated by the generator.

## Prepare and review

Choose absolute local paths for the interpreter, host JSON config, existing
user-data directory and dedicated log directory. Prepare the log directory with
owner-only permissions. Avoid shared/network folders. Paths with spaces or
accents are supported; quote each shell argument. The generator validates host
JSON but cannot prove that the chosen interpreter has AstroPilot installed:
verify that separately with that interpreter's `-m pip show astropilot`.

```sh
/absolute/venv/bin/python -m astropilot.opportunity_alert_launchd \
  --python /absolute/venv/bin/python \
  --config /absolute/opportunity-alerts.json \
  --data-dir /absolute/existing-user-data \
  --log-dir /absolute/dedicated-alert-logs \
  --throttle-seconds 60 \
  > /absolute/review/com.astropilot.opportunity-alert-host.plist
plutil -lint /absolute/review/com.astropilot.opportunity-alert-host.plist
```

Check the generator exit status before installing; shell redirection may leave
an empty file on validation failure. Optional `--state-dir` selects an explicit
scheduler state directory; normal deployments retain the host default. Review
paths and policy consent before activation. Existing Field Lab/NAS agents are
independent and must not be changed. Do not register multiple alert jobs against
one data directory. Logs and plist are owned by the login user; no sudo required.

## Operator installation (not performed by tests or generator)

Copy the reviewed plist to
`~/Library/LaunchAgents/com.astropilot.opportunity-alert-host.plist` with owner-only
permissions; create LaunchAgents if needed. Then explicitly activate:

```sh
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.astropilot.opportunity-alert-host.plist"
launchctl print gui/$(id -u)/com.astropilot.opportunity-alert-host
```

The unique label prevents loading the same job twice. The host lifetime lock
also prevents a manual or differently labelled duplicate for the same data dir.
`launchctl print` exposes PID/state and last exit; `kill -0 PID` checks that PID
is alive (substitute the reported numeric PID). Read the dedicated stdout JSON
for startup/cycle/shutdown events, stderr for interpreter/import diagnostics.
A persistent lock file is not evidence of a running host. No health HTTP server.

## Stop, start, update and logs

For an intentional operator stop/unload, use:

```sh
launchctl bootout gui/$(id -u)/com.astropilot.opportunity-alert-host
```

launchd sends SIGTERM directly, and waits up to 120 seconds before forced kill.
The host completes an active cycle before exiting. A raw SIGTERM with clean
exit 0 also stays stopped for this loaded session. A nonzero exit or crash is
eligible for relaunch. The throttle limits launch frequency to once per configured
30..3600 seconds; it is not exponential and not an exact post-exit sleep.
A failed startup/configuration can retry indefinitely at that limited frequency:
bootout, fix the problem and bootstrap again. Do not use `kickstart -k` for
routine shutdown; it can forcibly replace a process.

After bootout, edit config or regenerate/review the plist; bootstrap loads it
again. A stopped loaded job can be explicitly started with
`launchctl kickstart gui/$(id -u)/com.astropilot.opportunity-alert-host`.
Bootout alone does not remove next-login autostart: remove the installed plist
while unloaded to disable it persistently. No automatic OS installation occurs.

launchd appends stdout and stderr to the two dedicated log files. Logs have no
automatic retention limit in V1. Bootout, archive/rotate both logs, then bootstrap
to reopen paths. Keep scheduler state/ledger and lock file intact. Inspect free
space and JSON cycle errors during operation; liveness is not business readiness.

## Native acceptance checklist (requires explicit deployment)

Not executed during this PR, to avoid installing or activating a job:

- Installed wheel/interpreter launches from an unrelated cwd.
- Bootstrap and next login start exactly one host; second bootstrap is rejected.
- Manual duplicate exits 1 without evaluating a cycle.
- Kill the host to simulate crash; launchd relaunches according to its throttle.
- SIGTERM yields shutdown JSON and exit 0, with no automatic respawn in session.
- Bootout stops/unloads; bootstrap starts it again without a duplicate.
- Confirm PID, exit diagnostics, deterministic logs and 120-second stop behavior.
- Confirm installed alert plist is independent of every Field Lab/NAS job.

Restart does not replay missed scheduler slots or change alert suppression.
No push, email, mobile or webhook notification is sent. Notification v1 follows
this PR after merge, in a separate change.

Native policy reference:
[Apple launchd.plist manual](https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5).
