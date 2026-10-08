# Opportunity Alerts process host v1

Baseline: #335 merged at 2cf4b9bec134490db0043f33ebe0149602310920.

A dedicated foreground process hosts the existing scheduler. Invocation is
explicit: `python -m astropilot.opportunity_alert_host --config /absolute/config.json
--data-dir /absolute/user-data`. It starts no API server or browser and installs
no service. One process owns this user-data context, with a nonblocking lifetime
lock; a duplicate host exits with a stable diagnostic. The scheduler's own
cross-process reservation remains authoritative for slot attempts.

The configuration is strict, versioned JSON, read once at startup. Schema,
positive integral interval_seconds, policy and availability are required; unknown
or duplicate keys, naive timestamps, non-finite numbers and invalid domain values
fail before runtime state writes. Policy defaults remain disabled; enabling
requires existing domain selectors and explicit session availability. Configuration
changes require process restart. Changing cadence requires an explicit new
scheduler state directory (`--state-dir`), never automatic reset.

Each due cycle lazily loads the current existing user profile, resolves Tonight
inputs using its existing resolver, acquires weather once with the production
provider and evaluates the existing Tonight service at most once through the runner.
If weather acquisition returns None, preparation fails without entering Tonight:
the existing forecast helper's implicit second acquisition is never triggered.
Preparation lives in an injected Tonight adapter, inside the reserved cycle. It
is never executed for disabled policy, skipped/repeated slots or overlap. No
engines, decision transport, durable Tonight side stores, Field Lab or NAS APIs
are invoked by the host. The existing alert ledger uses the user data directory;
the scheduler watermark lives in a separate opportunity_alert_scheduler directory.
The host never writes the profile or creates missing profile defaults.

At startup the scheduler polls the current slot. The host supplies cycle_time equal to the injected current UTC time, separately
from the slot start retained in the watermark. This prevents fresh mid-slot
weather from being rejected as future data. Scheduler default callers retain
slot-start logical time; an override outside the current slot is rejected.
The serial loop then waits for
the next slot with an injected Event.wait and aware UTC clock. Waits are capped
at 60 seconds to notice forward wall-clock jumps; backward times cannot replay
slots. Long cycles and downtime skip missed slots without bursts. No polling
queue or background cycle workers. Runner/preparation/scheduler ERROR is logged
once for that slot; the next slot still runs. No immediate retry.

SIGINT and SIGTERM set a stop event, interrupt waits, and allow an active cycle
to finish. Signal handlers are restored and the lifetime lock released on exit.
A stuck external dependency can delay shutdown; the production weather provider's
existing timeout behavior remains unchanged. A supervisor may impose a final
kill timeout; the existing reservation/ledger still suppresses replay after kill.

Diagnostics are JSON lines to stdout (startup, cycle, shutdown), with allowlisted
status, slot, evaluation logical_time and generic reason only. Legacy helper stdout/stderr is discarded inside the serial preparation adapter.
No profile, location, exception
text, weather or alert payload. A claimed alert remains a ledger claim without
any delivery channel. Exit 0: graceful stop/one-shot successful orchestration;
exit 1: startup failure, duplicate host or one-shot cycle ERROR; argparse syntax
errors exit 2. `--once` runs one scheduler poll and exits for deployment checks.

This PR provides an executable process host and its operator instructions.
OS auto-start/supervisor installation, application UI opt-in, hot reload,
distributed hosting, notification and Field Lab/NAS remain outside scope.
