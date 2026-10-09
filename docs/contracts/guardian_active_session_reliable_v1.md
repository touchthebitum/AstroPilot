# Guardian active-session context reliable v1

The application or explicit caller is the only authority for session state. This
increment supplies local persistence and an opt-in host adapter for the existing
`guardian-live-session-v1` contract. It does not discover sessions or infer them
from weather, ASIAIR, processes or network activity. It performs no hardware action.
Risk levels, action rules, Open-Meteo, Field Lab and NAS are unchanged.

## Explicit writer

The caller writes on explicit start/stop and renews its own attestation while it
can still assert the state. ACTIVE and INACTIVE both expire. The library never
chooses a heartbeat timestamp, renews evidence during reads, or assumes INACTIVE
when the file disappears. One application/caller should own the authoritative
path. Concurrent writes use last atomic replacement; multi-writer arbitration is
outside v1. No UI, HTTP endpoint or automatic acquisition lifecycle is added.

```python
from datetime import datetime, timezone
from astropilot.guardian_session_store import GuardianSessionStore
from decision.models.guardian import GuardianSessionState
from decision.models.guardian_live_session import GuardianLiveSessionEvidence

store = GuardianSessionStore('/absolute/local/path/session.json')
store.write(GuardianLiveSessionEvidence(
    state=GuardianSessionState.ACTIVE,  # explicit stop: INACTIVE
    observed_at=datetime.now(timezone.utc),
    source='caller_session_heartbeat_v1',
    provenance='CALLER_ASSERTED',
    session_id='caller-owned-session-id',
))
```

The JSON envelope has exactly these fields:

```json
{
  "schema_version": 1,
  "version": "guardian-live-session-v1",
  "source": "caller_session_heartbeat_v1",
  "provenance": "CALLER_ASSERTED",
  "state": "ACTIVE",
  "observed_at": "2026-10-09T16:00:00+00:00",
  "session_id": "caller-owned-session-id"
}
```

`state` accepts exactly ACTIVE, INACTIVE, UNKNOWN. `observed_at` must be an
ISO timestamp with timezone. `session_id` is null or a nonempty string. Booleans
are not schema versions. Extra/missing fields, duplicate keys, malformed UTF-8,
invalid JSON and files exceeding 16 KiB are rejected. The writer validates before
mutation, flushes and fsyncs a temporary file in the destination directory, then
uses atomic replacement and cleans up its temporary file. This prevents partial
reads; it is not a promise of directory-entry durability across power loss.
Writer errors propagate; a failed replacement leaves the old file intact.

## Reader and host

`GuardianSessionStore.read(logical_time)` returns existing typed evidence only
when its state is ACTIVE or INACTIVE and its age is in **[0, 900] seconds**.
UNKNOWN, absent, unreadable, corrupt, future or stale evidence returns `None`.
Each read opens the file anew; there is no cached last-good fallback. Restarting
retains the original timestamp and cannot extend validity.

Add this optional field to the existing host configuration:

```json
"session_context": {
  "provider": "local_session_attestation_v1",
  "path": "/absolute/local/path/session.json"
}
```

The path must be absolute. A malformed opt-in configuration fails startup. A
valid configuration selects this session provider independently of the evidence
provider, including the built-in live weather adapter. Omitting the field keeps
existing built-in and injected session behavior. A disabled host never reads the
attestation. The host does not create or update it.

The store's callable adapter raises a sanitized `session_context_unavailable` on
unknown input. The existing periodic runner catches it as `session_provider_error`:
cycle ERROR, session UNKNOWN, applicability UNKNOWN, decision ineligible,
recommended EMERGENCY_STOP. A foreground host resumes at the next scheduled slot
under its existing transient-error contract; `--once` exits 6. Fresh INACTIVE
means NOT_APPLICABLE, never an inferred shutdown. Weather risk assessment remains
independent. Losing session evidence cannot improve a cycle recommendation or
retain decision eligibility. All actions remain recommendations only.

No new dependency, provider HTTP request, hardware control, API or UI is introduced.
