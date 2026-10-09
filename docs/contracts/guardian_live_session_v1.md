# Guardian live session evidence v1

## Local audit
Guardian host process/lock and scheduler cycle timestamps attest monitoring only.
The production weather factory supplies no session context. Mission IDs and
acceptance/progress records describe planning or historical work, not a live
acquisition. No existing ASIAIR/mount session telemetry or acquisition heartbeat
provider is wired to Guardian. None of these imply ACTIVE or INACTIVE.

## Evidence and evaluation
Immutable GuardianLiveSessionEvidence: version guardian-live-session-v1, state
ACTIVE/INACTIVE/UNKNOWN, aware observed_at, source caller_session_heartbeat_v1,
provenance CALLER_ASSERTED, optional nonblank opaque session_id. observed_at is
the heartbeat observation time; a second last_activity_at would duplicate it.
Only this allowlisted source/provenance pair is supported. It is an explicit
caller attestation, not authenticated hardware telemetry. ACTIVE means the caller
explicitly attests acquisition is ongoing; INACTIVE means it explicitly attests
acquisition is stopped. Merely running the Guardian host is neither assertion.

Both assertions require age 0..900 seconds inclusive (existing provisional
session-v1 freshness default, independent of weather policy). Missing, stale,
future, malformed, unsupported version/source/provenance or explicit UNKNOWN
produces UNKNOWN applicability. Reasons remain separate from environmental
reasons. Raw evidence is retained in session_context. Same environmental evidence
always produces same risk/action regardless of session. Guardian never authorizes
a session or executes a recommendation.

The existing guardian-session-v1 context and explicit boolean interface remain
caller assertions for compatibility; they are not upgraded to live telemetry.
The new evidence is injectable through the existing domain runner/provider seam;
no automatic source discovery, new API/UI, host wiring, hardware, notifications,
Tonight, Opportunity Alerts or Field Lab/NAS integration.
