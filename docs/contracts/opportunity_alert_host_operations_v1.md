# Running the Opportunity Alerts host

Use the Python environment in which AstroPilot is installed. The process is
independent of `astropilot-app`; it runs cycles automatically while it is alive.
It does not install auto-start or change any existing Field Lab/NAS service.

## Configuration

Save a separate JSON file. This disabled configuration is a safe startup check:

```json
{
  "schema_version": 1,
  "interval_seconds": 3600,
  "policy": {},
  "availability": null
}
```

For enabled operation, explicitly provide the existing policy selectors and
session availability. Replace these example identities with actual profile
identities; they are not resolved or invented by the host:

```json
{
  "schema_version": 1,
  "interval_seconds": 3600,
  "policy": {
    "enabled": true,
    "site_name": "Buttes",
    "project_keys": ["Sh2-129"],
    "intent_ids": ["sh2-129_ha"],
    "filter_profile_ids": ["actual-setup-filter-profile-id"],
    "cooldown_minutes": 1440
  },
  "availability": {"mode": "all_night"}
}
```

`all_night` is explicit consent to evaluate the whole night for the configured
context. Other supported availability modes use the existing domain contract:

| mode | required fields |
| --- | --- |
| all_night | none |
| duration | duration_seconds (positive integer) |
| start_and_duration | start, duration_seconds |
| until | end |
| fixed_window | start, end |

Times are ISO 8601 with an explicit timezone, normalized to UTC. Fixed windows
are absolute, not recurring local-time rules. They expire according to existing
Tonight guards. Stop/restart with new configuration when availability changes;
policy time windows are also absolute. No automatic consent or inferred window.

## Start and stop

```sh
python -m astropilot.opportunity_alert_host \
  --config /absolute/opportunity-alerts.json \
  --data-dir /absolute/existing-user-data \
  --once
```

`--once` performs a real scheduler poll and may claim an alert when enabled. It
is not a dry run. Use the disabled configuration above for a no-business-I/O
startup check. A successful poll reserves that slot; enabling within the same
slot will wait until the next slot unless you intentionally choose a new state
store. Do not delete suppression state to force an alert.

Remove `--once` for continuous operation. Keep the process attached to a terminal
or run this same command under a separately configured supervisor. The working
directory is irrelevant; pass explicit configuration/data paths and the correct
Python executable. Ctrl+C or SIGTERM interrupts the wait and lets an active
cycle finish. No hard exit in the signal handler.

By default the scheduler watermark is in
`<data-dir>/opportunity_alert_scheduler/opportunity_alert_scheduler.json`,
while the existing ledger remains `<data-dir>/opportunity_alert_ledger.json`.
The lifetime lock is `<data-dir>/.opportunity_alert_host.lock`. Lock files remain
after exit and are reused; their presence alone does not indicate a live host.

The data directory must match the user/context used by the API alert ledger.
One host per user data directory; another host fails immediately. Do not share
these files through network/distributed filesystems. Cadence mismatch or corrupt
state fails closed; no reset or recovery is automatic. Preserve the ledger when
changing cadence. A new cadence needs an explicit unused `--state-dir`; the
ledger still suppresses already-claimed alerts.

JSON diagnostics go to stdout. A supervisor may capture/rotate them externally.
Inspect `status`, `cycle_status`, `slot` and `logical_time`:

- COMPLETED + ALERT_EMITTED: durable ledger claim; delivery has a separate notification event.
- COMPLETED + NO_ALERT: existing Tonight/policy guards declined or disabled.
- COMPLETED + ERROR: runner/preparation failed; no immediate retry.
- ERROR: scheduler state unavailable/corrupt; no runner attempt when reservation fails.
- SKIPPED: slot already reserved/completed (including restart).

Errors contain stable generic codes. Exit 1 on startup errors, duplicate host or
one-shot cycle failure; the continuous process stays alive after cycle ERROR and
tries the next slot. Monitor JSON cycle errors if operating under a supervisor:
process liveness alone does not prove successful evaluation. Exit 0 on graceful
stop; command syntax errors exit 2.

The host loads configuration once, but reloads the existing profile on each
reserved enabled cycle. It reads current preferences/equipment and acquires
weather through the existing production helper (15-second HTTP timeout). A failed
acquisition stops that cycle without entering Tonight's implicit weather retry. It
never writes the profile, rewrites weather timestamps or changes freshness
thresholds. A startup at 12:45 uses slot 12:00 for deduplication and logical_time
12:45 for live evaluation. No missed-slot burst occurs after restart or a long
cycle. A killed process can lose its reserved cycle; the next slot is eligible.

No service is installed or started automatically by this PR. Supervisor/OS
auto-start deployment remains an operator action. No push, email, webhook or
other notification channel is provided by the host core; optional macOS delivery is described below.

For the opt-in macOS user-login integration, see
[LaunchAgent operations](opportunity_alert_launchd_operations_v1.md) and the
[supervision contract](opportunity_alert_supervision_v1.md). Generation performs
no installation; Windows autostart remains a separate deployment change.

## Optional notification channel

See [notification v1](opportunity_alert_notification_v1.md) for the opt-in
`notification_channel` config key, separate delivery results and macOS limitations.
The default remains disabled.
