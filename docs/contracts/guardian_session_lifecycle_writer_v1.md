# Guardian session lifecycle writer integration v1

## Audit at 55a9ac46cc0353acee3e09b194d876ea3586c929

NightMerit has explicit user execution commands: `startSession` and `closeSession`
in `astropilot/web/app.js` send `/v1/execution-transitions` to
`astropilot/app.py`. `ExecutionOutcomeApplicationService.transition_execution`
validates transitions and persists them in the execution lineage store.
`ExecutionStatus` distinguishes NOT_STARTED, IN_PROGRESS, COMPLETED, INTERRUPTED
and UNCONFIRMED. These records also serve history and outcome recording; an
IN_PROGRESS record is not a continuously observed acquisition signal.
`SessionRecordingService` records historical integration, not live acquisition.

There is no durable acquisition owner or explicit live renewal command in the
current UI/service. Guardian's scheduler owns assessment cycles, not acquisition.
Therefore this increment supplies an opt-in explicit caller around the real
execution command boundary. It does not automatically wire historical transitions
or browser presence into Guardian. The default UI/API remains unchanged. Production
activation requires a caller that can actually attest ongoing acquisition; this
increment does not claim full unattended lifecycle integration.

## Caller contract

`GuardianSessionLifecycle(execution_service, GuardianSessionStore(path))` is owned
by a single caller, with a dedicated authoritative path shared with Guardian's
existing `session_context` provider. Only one execution can be live per caller.
All command timestamps are explicit timezone-aware observations from that caller.

- `start(destination, observed_at=...)`: destination is the user's IN_PROGRESS
  execution command. The real execution service validates/persists it first; only
  success writes ACTIVE with the execution ID and establishes local ownership.
- `renew(execution_id, observed_at=...)`: explicit confirmation by that same live
  caller. Requires its local ownership, an IN_PROGRESS execution and an existing
  fresh ACTIVE attestation of the same ID. It cannot revive missing, expired,
  future, corrupt or UNKNOWN evidence. Repeating the same renewal is idempotent.
- `stop(destination, observed_at=...)`: explicit COMPLETED or INTERRUPTED command
  through the execution service, followed by INACTIVE. It can close an execution
  after caller restart. UNCONFIRMED is not an attestation of stopped acquisition.

Construction does not read or write, and restart cannot recover renewal ownership
from historical records. Duplicate start/stop commands retain the real service's
transition rejection behavior and never silently extend freshness. No background
thread, daemon, timer, hardware action or inference is introduced. A lock serializes
this caller's operations; cross-process/multiple-caller arbitration is outside v1.
Deployments must give this caller exclusive ownership of the path and execution
commands; bypassing it can only lose trustworthy context, not justify renewal.

## Failure and freshness

Write errors propagate. Ownership is revoked and the caller attempts removal of
last-good evidence so a failed stop cannot leave favorable evidence. A removal
failure also propagates with the original exception in its context. Execution
persistence and attestation are not a transaction: execution may have committed
when attestation publication fails; callers must surface that failure and not
report Guardian synchronization as successful. If the filesystem refuses both
write and removal, the old file can survive until its original expiry; no local
file protocol can promise immediate revocation under that failure. No retry or
renewal is scheduled to conceal this limitation.

The existing store/host retains 900-second freshness, no synthetic read timestamps,
UNKNOWN on loss, fail-closed recommendation and no cached last-good fallback.
Both ACTIVE and INACTIVE expire. Risk/action rules, Open-Meteo, Field Lab and NAS
are unchanged. Start after expiry requires a new explicit execution start; merely
restarting the caller cannot restore eligibility.

```python
from astropilot.guardian_session_lifecycle import GuardianSessionLifecycle
from astropilot.guardian_session_store import GuardianSessionStore

caller = GuardianSessionLifecycle(execution_service,
    GuardianSessionStore('/absolute/local/path/session.json'))
caller.start(user_start_execution, observed_at=user_start_observation)
# Only while this owner explicitly confirms acquisition is still live:
caller.renew(user_start_execution.execution_id, observed_at=live_observation)
caller.stop(user_closed_execution, observed_at=user_stop_observation)
```
