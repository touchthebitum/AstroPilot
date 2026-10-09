# Guardian host/process v1

Foreground orchestration only. CLI: `python -m astropilot.guardian_host
--config CONFIG --data-dir DATA [--state-dir STATE] [--once]`.
No OS autostart, notification, hardware, network acquisition, Tonight,
Opportunity Alerts, Field Lab or NAS integration.

## Configuration and providers

Strict UTF-8 JSON object: `schema_version` (integer 1), `interval_seconds`
(positive integer), `anchor` (aware ISO timestamp), optional `enabled` (boolean,
default false), optional `provider` (registry identifier, default null).
No unknown/duplicate fields, coerced values or nonfinite numbers. Cadence is
normalized to UTC and must match the existing durable store.

An enabled host requires an explicit provider identifier. Embedders call
`main(argv, provider_factories={identifier: factory})`. Each trusted factory
receives no arguments and returns `GuardianHostProviders(evidence, session)`;
both callables receive the slot time under the periodic runner contract.
There is no dynamic import or automatic provider discovery. The standalone CLI
has an empty registry: enabled acquisition fails with `provider_unavailable`.
This V1 is not production-ready for live acquisition. Providers must be bounded,
cooperative synchronous adapters; no host-owned threads/processes or retries.
Default GuardianPolicy remains owned by GuardianRunner, not the host config.

## Authority and lifecycle

The #350 persistent scheduler alone claims slots; #348 periodic runner alone
acquires/evaluates. State lives at `(STATE or DATA)/guardian_scheduler/state.json`.
A separate nonblocking lifetime lock `DATA/.guardian_host.lock` prevents two
hosts on the same canonical data directory even with different state roots.
Shared state across different data roots remains protected by the scheduler lock.
Never unlink lock files. No catch-up: one poll of the current slot, then wait for
the next boundary. Overruns skip elapsed slots. Restart polls once but durable
claims prevent replay, including failed/crashed cycles.

SIGINT/SIGTERM set a stop event. Wait is interruptible, capped at 60 seconds for
wall-clock adjustments. A running synchronous cycle finishes before shutdown;
providers cannot be forcibly interrupted. Signal handlers and locks are restored
on every exit. No orphan threads/processes. Fatal cycle/state errors stop the
host; there is no hidden retry. Disabled config exits without providers or state.

## Diagnostics and exits

JSON lines only: startup (`config_version`, `enabled`, `interval_seconds`,
`anchor`), cycle (`slot`, scheduler `status`/`reason`, `cycle_status`, `risk`,
`action`, `decision_eligible`, `session_state`, `session_applicability`, `errors`),
error (`reason`), shutdown. No paths, IDs, evidence, exception text or traceback.
Enums serialize by name, including UNKNOWN. Cycle action/eligibility use the
periodic result; an ERROR always emits EMERGENCY_STOP and false eligibility,
even if its embedded assessment would otherwise be favorable.

Exit 0: normal/disabled/cooperative stop, successful or skipped once poll.
Exit 2: config/CLI error. Exit 3: unavailable/invalid/failing provider factory.
Exit 4: duplicate host or host lock failure. Exit 5: scheduler state failure.
Exit 6: cycle/provider/evaluation ERROR, including `--once`. Exit 1: unexpected
host failure. Public reasons are stable allowlisted codes. After startup, every
exit emits shutdown; errors also emit error. `--once` performs at most one poll.

## Minimal disabled configuration

```json
{"schema_version":1,"interval_seconds":60,"anchor":"2026-10-09T00:00:00+00:00"}
```

Enable only with `"enabled":true,"provider":"your_adapter"` and an explicit
trusted registry supplied by the embedding entrypoint. Factories must return
synchronous callables without background workers; provider output is suppressed
while constructing dependencies and polling. OS supervision/autostart or Guardian
notifications should be separate follow-ups after a stable live adapter exists.
