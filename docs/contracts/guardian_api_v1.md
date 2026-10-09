# Guardian runner/API v1

POST /v1/guardian/evaluate evaluates only injected observations. No live GET,
storage, polling, notification, hardware, network discovery or authorization.
The pure runner takes observation, session context, aware now and server policy;
it calls assess_guardian exactly once and returns the frozen GuardianAssessment.
The transport supplies its server clock. Clients cannot override now or policy.

Input: observations (six optional evidence fields: rain_active, rain_eta_minutes,
wind_kmh, gust_kmh, humidity_percent, dew_spread_c), and required nullable
session_context (session_active boolean, observed_at aware timestamp). Each
supplied evidence has value, source (nonblank, maximum 128 characters), provenance
OBSERVATION or FORECAST, and aware timestamp. Rain is strict boolean; numeric
values are finite numbers, never strings or booleans. Only rain_eta_minutes may
have null value (explicit no forecast rain). Extra fields are forbidden at every
level. No identifiers or policy overrides. Missing evidence is deliberately valid
input so Guardian can express UNKNOWN. Invalid ranges, future or stale evidence
remain UNKNOWN/EMERGENCY_STOP; malformed or naive timestamps return 422.
Null, stale or future session context remains visible UNKNOWN without
changing environmental risk/action. decision_eligible describes environmental
evidence completeness only; it never grants authority to start a session.

Output is allowlisted: schema_version guardian-api-v1, policy_version guardian-v1,
risk_level, recommended_action, session_state, action_applicability,
decision_eligible, evidence_complete, reasons, session_reasons and assessed_at.
Reasons are restricted to Guardian v1 codes. UTC timestamps serialize with Z.
No source strings, session identifiers, thresholds, internal objects or hardware
details are echoed. Validation errors: 422 invalid_guardian_request. Unexpected
evaluation/serialization failures: 500 guardian_evaluation_failed, without a
favorable decision or exception detail. A server-configured policy is injected at
application construction, defaulting to GuardianPolicy; never request-scoped.

Tests must cover single invocation, immutability, rain critical, missing/stale/
future evidence, strict schema, session independence, removal monotonicity, UTC,
allowlisted reasons, sanitized failures and dependency boundaries. V1 is a caller
assertion, not verified telemetry. A separate periodic runner or notification
contract may follow; neither is introduced here.
