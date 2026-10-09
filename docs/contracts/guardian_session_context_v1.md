# Guardian active session context v1

Guardian separates environmental assessment, caller-supplied session context and
recommendation applicability. Risk, action, reasons, evidence and policy remain
independent of session state. Guardian never authorizes a start or executes an
action. hardware_action remains None.

GuardianSessionContext is immutable: version guardian-session-v1, strict boolean
session_active, aware observed_at and optional nonempty opaque session_id.
The caller supplies now; no clock, session discovery or I/O is introduced.
Context freshness is explicitly 900 seconds inclusive in v1, independent of the
environmental policy. Future, stale, unsupported or malformed context is UNKNOWN.
Missing context is UNKNOWN. Provenance is retained as supplied in session_context;
no identifier participates in risk scoring or applicability.

| Risk | Recommendation | ACTIVE | INACTIVE | UNKNOWN |
| --- | --- | --- | --- | --- |
| SAFE | CONTINUE | APPLICABLE | NOT_APPLICABLE | UNKNOWN |
| WATCH | MONITOR | APPLICABLE | NOT_APPLICABLE | UNKNOWN |
| WARNING | PREPARE_STOP | APPLICABLE | NOT_APPLICABLE | UNKNOWN |
| CRITICAL | STOP_SESSION | APPLICABLE | NOT_APPLICABLE | UNKNOWN |
| UNKNOWN | EMERGENCY_STOP | APPLICABLE | NOT_APPLICABLE | UNKNOWN |

operationally_applicable is true only for APPLICABLE. false with UNKNOWN is not
proof of inactivity or permission to ignore risk. session_active is None for
UNKNOWN. Removing context can never improve risk/action. Separate session_reasons
explain missing, invalid or stale context without changing environmental reasons.

The existing explicit session_active boolean call remains supported as a caller
assertion observed at now. Omitted context is unknown; invalid legacy booleans
still raise ValueError. Supplying both interfaces raises ValueError, including
explicit None, so conflicting assertions cannot be silently preferred.
No hardware/API/UI/notification/scheduler, Tonight, Opportunity Alerts or Field
Lab/NAS dependency. Context is an assertion, not independently verified telemetry.
Next step: a separate read-only API/runner to supply context and expose this
contract; consumers must handle UNKNOWN explicitly. No hardware automation.
