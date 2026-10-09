# Guardian periodic runner v1

Version: `guardian-periodic-v1`. This is a caller-driven single-cycle application
boundary, not a scheduler. The caller invokes `run_cycle(logical_time=...)` with
an aware datetime. Invalid logical time raises ValueError before any dependency
is called. No wall clock, persistence, retries, sleeping, networking, hardware,
notifications, Tonight, Opportunity Alerts, Field Lab or NAS integration.

## Injected dependencies

Evidence and session providers each receive the same logical time, once per
valid cycle, even when the other provider fails. Evidence must be a
GuardianObservation: an empty/incomplete observation is valid evidence, whereas
None, a wrong type or an exception is an acquisition error. Session may be a
GuardianSessionContext or None (valid unknown session); a wrong type or exception
is an acquisition error, replaced with None. Providers own their acquisition;
the runner never discovers or constructs live providers.

GuardianRunner.evaluate is called exactly once when an observation was acquired,
including session acquisition failures; zero times on evidence acquisition
failure. No retry. The default GuardianRunner calls assess_guardian once.

## Immutable cycle result

- ASSESSED: successful acquisition/evaluation, including incomplete evidence and
  unknown/invalid/stale session data handled by existing domain validation.
- ERROR: evidence_provider_error, session_provider_error or evaluation_error.
  Codes are ordered evidence, session, evaluation; no exception text is exposed.
- assessment: existing GuardianAssessment when evaluation succeeded, otherwise
  None. A session provider failure retains the evidence risk/action and produces
  UNKNOWN session/applicability. It never changes the evidence risk.
- logical_time and version: explicit cycle metadata; no generated identifiers.
- decision_eligible: false for every ERROR; otherwise existing assessment flag.
- recommended_action: EMERGENCY_STOP for every ERROR; otherwise assessment action.

The cycle recommendation is authoritative for cycle consumers. An assessment
inside ERROR is diagnostic and must not be treated as authorization to continue.
No SKIPPED/cadence policy in v1: scheduling and cycle deduplication belong to a
future orchestrator. Each invocation is one logical cycle; repeated invocations
are independent and return equal results for equal time and provider outputs.
UNKNOWN always preserves EMERGENCY_STOP. No hardware execution authority.

Exceptions derived from Exception are converted to error codes; process-control
exceptions propagate. An invalid evaluator result is evaluation_error. The
injected evaluator must implement the existing GuardianRunner contract.
