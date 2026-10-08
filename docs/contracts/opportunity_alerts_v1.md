# Intelligent Opportunity Alerts v1

## Baseline and boundary

Baseline: main/origin/main d7369ed5727cdb293a5b44246bef09f63a8b842d,
merge of #330. Critical stash 223ec1f5904131d726b694655f137670c0ddeb0b
is preserved in existing historical repositories. Work occurs in an isolated
clone. No Field Lab, NAS, notification channel, API or profile migration.

Consume TonightApplicationService's live AVAILABLE result, after recommendation,
modern mission authorization, continuous actionability and consistency validation.
Retain the existing MissionInput and ProductiveWindowAssessment internally; never
rerun weather, lunar, ranking, gain or productive-window engines for an alert.
A process-local marker distinguishes live evaluation from historical/read-only
results. A missing marker or retained evidence always fails closed. This is an
internal accidental-replay guard, not a Python security sandbox.

## Outcomes and minimal policy

OpportunityAlert is an immutable session_opportunity object, distinct from a
mission. OpportunityAlertDecision has exactly ALERT and NO_ALERT, with reason
codes and an optional alert. No previews in v1. Availability is mandatory.

OpportunityAlertPolicy schema_version=1 is separate from the current user profile.
Disabled by default. Explicit enabled policy requires a site name and nonempty
allowlists of catalog project keys, acquisition intents and resolved optical
profile IDs. Site name uses Tonight's current identity contract (not a global
site UUID). min_expected_gain is in Tonight's existing gain units; strictly
positive gain is always required. min_duration_minutes >=60; min_quality in
0..100 uses only complete AQI decision_score. No arbitrary ranking score threshold.
Optional aware absolute time bounds must contain the entire selected session;
no clipping, timezone guessing or recurring-time UX. Invalid policy is rejected.

Require: live AVAILABLE output; recommendation; modern creation authority bound
to field/intent/capacity; eligible selected intent; resolved optical profile;
matching project/field/intent/mission/decision/selection identity; retained complete
ProductiveWindowAssessment; selected window inside one continuous productive
interval and source horizon; positive duration and gain bounded by assessment;
complete decision-eligible AQI (partial diagnostic score never qualifies).
Reuse existing authorization and mission consistency validators; do not infer
unknown evidence or accept legacy provenance. Missing any proof yields NO_ALERT.
Lunar snapshots are required only where existing selection contracts require
them, and must match the already selected candidate/input/mission snapshots.

## Idempotence and logical cooldown

Caller supplies an explicit aware logical evaluation time, never system now.
Stable SHA-256 key: schema/project/field/intent/site/filter/profile/window UTC /
decision and selection lineage. Exact keys are claimed at most once. A broader
project/field/intent/site/profile family cooldown suppresses a reissued lineage
or slightly shifted window. Default cooldown 24 hours, measured on caller's
logical timeline. Older/out-of-order logical evaluations fail closed. Policy
changes do not change identity. Refusals do not consume claims.

InMemoryOpportunityAlertLedger atomically claims under a lock. It is scoped to
one user and retained across hourly evaluations by the caller. Restart durability,
multi-process storage and eviction are deferred; production scheduling must use
a durable atomic ledger before notification delivery. No alert is sent in v1.

## Validation and next step

Tests first: absent recommendation/availability, short continuous window,
nonpositive gain, intent/profile/evidence failures, complete positive control,
evidence deletion monotonicity, stricter-policy monotonicity, exact/family
idempotence, logical cooldown, read-only/legacy rejection and live integration.
Run architecture and full relevant suite, diff hygiene and Field Lab scope audit.
Next PR: durable per-user ledger and explicit API transport; channels follow.

## Internal use

Keep a single per-user ledger/service across logical evaluations. Evaluate Tonight
normally, then call `OpportunityAlertService.evaluate(result=tonight_result,
policy=policy, logical_time=reference_time_utc)`. The result has status, reason_codes,
and alert; callers must not use mission/recommendation transport DTOs as input.
The service is intentionally not installed in an hourly scheduler in this PR.
An explicit policy might enable project Sh2-129 / sh2-129_ha at Buttes with the
resolved optical profile, min_expected_gain=10, min_duration_minutes=90 and
min_quality=80. All thresholds are conjunctive. Modern expected_gain is percentage
of the selected acquisition intent target (not total project or diagnostic score).
Never create a fresh in-memory ledger for each hourly evaluation.

## Architecture / changed paths

- decision/models/opportunity_alert.py: immutable policy, alert and decision.
- decision/services/opportunity_alert_service.py: consume/validate existing evidence,
  policy conjunction, stable UTC identity, atomic ledger protocol and memory adapter.
- decision/mission/mission_assembler.py: retain the already computed assessment in
  the diagnostic assembly result; mission behavior is unchanged.
- decision/services/tonight_application_service.py: retain internal evidence and
  mark only the final validated AVAILABLE live result. Refused and fallback results
  never acquire usable alert evidence. Public TonightResponse stays unchanged.
- tests/architecture/test_opportunity_alerts_v1.py: positive control and refusal,
  deletion, stricter policy, concurrency, replay and live integration checks.

A full AQI is mandatory even when min_quality=0. Temperature evidence is retained
alongside productive weather inputs because AQI dew evidence depends on it.
The logical evaluation time must precede the selected session start; v1 never
alerts for an already started session. Identity is normalized to UTC, including
policy and availability comparisons. Exact emitted keys remain suppressed beyond
cooldown; a new lineage/window may emit only once cooldown expires.
