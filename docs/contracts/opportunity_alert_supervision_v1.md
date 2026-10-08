# Opportunity Alerts supervision / autostart v1

## Deployment decision (before implementation)

Baseline: main == origin/main == 9e3e87b2e9357fdbd9842a58e3c527343c12f40e,
PR #336 merged. Work is in an isolated clone. The historical repository's
stash 223ec1f5904131d726b694655f137670c0ddeb0b must remain untouched.

The existing foreground module is portable Python; the packaged GUI launcher
is not a generic Python module launcher. macOS and Windows packaging exist,
but no Windows Opportunity Alerts service or Task Scheduler integration exists.
A Python supervisor would still need an OS autostart integration and introduce
another process, signal relay and orphan ownership. V1 therefore generates a
macOS user LaunchAgent that directly supervises the existing foreground host.
The generator is portable/testable Python, but the generated deployment is
macOS-only. Windows 11 autostart is a separate PR; Linux, Android and iOS are
out of scope. No Field Lab service code, configuration or installation is reused.

## Contract

- Generation only: emit an XML plist to stdout; never install, invoke launchctl,
  create user data/log directories, or start a host. Operator reviews the result.
- Fixed label `com.astropilot.opportunity-alert-host`; one job per login user.
- Absolute interpreter, config, existing data directory and existing dedicated
  log directory required; optional absolute state directory. No shell, PYTHONPATH
  or source checkout dependency. Use Python with AstroPilot installed.
- Config is validated by the host's existing parser before emission. Interpreter
  must be executable. Config/data/log/state must be distinct where applicable;
  log files cannot overwrite configuration. Symlink aliases are canonicalized,
  except the Python executable (preserve virtual-environment identity).
- `RunAtLoad=true`: start at login/bootstrap. `KeepAlive={SuccessfulExit:false}`:
  retry crash/nonzero; clean exit 0 remains stopped in that loaded session.
- Configurable fixed launchd throttle 30..3600 seconds, default 60. This bounds
  spawn frequency, not a guaranteed delay measured from each exit. A long-lived
  crashed process may restart immediately. No exponential backoff or retry cap.
- `ExitTimeOut=120`: launchd sends SIGTERM directly to the host, allowing its
  current cycle to finish; after 120 seconds launchd may SIGKILL. No signal relay.
- Duplicate label is rejected by launchd; the host's lifetime lock independently
  prevents two live hosts for the same data directory, including manual starts,
  alternate jobs and reloads. A competing job fails with exit 1 and is throttled;
  it can start later after the original host releases its lock. Remove competing
  jobs; do not use that behavior as ownership transfer.
- Dedicated append stdout/stderr paths: `opportunity-alert-host.stdout.log` and
  `opportunity-alert-host.stderr.log`. Unbuffered Python. No automatic rotation;
  stop/bootout before archiving logs so open descriptors do not retain old files.
- Liveness: launchctl print reports PID/state/last exit; kill -0 verifies PID.
  A lock file's existence alone is not readiness. JSON startup/cycle diagnostics
  indicate progress, but liveness does not guarantee successful business cycles.
- Generator fails immediately on invalid input. Later config/runtime errors
  produce existing host exit 1 and bounded launchd retries; bootout and fix them.
- No changes to host, runner, scheduler, business engines or notification delivery.

## Validation boundary

Tests assert the native policy keys, bounds, arguments and deterministic logs;
real subprocess tests exercise duplicate ownership, signal stop, crash lock
release, restart and output routing. They do not emulate or prove launchd's
implementation. Native bootstrap/login/restart validation remains an operator
check after review, because this PR never activates an OS job during tests.
Native semantics follow Apple's launchd.plist manual:
https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5
