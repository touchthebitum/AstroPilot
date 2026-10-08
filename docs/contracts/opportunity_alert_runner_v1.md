# Opportunity Alerts periodic runner v1

Baseline: #333 merged at 555d9ec41b539314f4235af1ab4d5c20b21345d6.

One runner instance is bound to one user's Tonight service and alert ledger.
The caller supplies an aware logical_time, policy and explicit Tonight inputs
(profile, weather, bortle, equipment, goal, target, availability). The runner
passes that time as reference_time_utc to exactly one Tonight evaluation and
consumes its live result with OpportunityAlertService, the internal boundary
used by #333. It never invokes engines or HTTP itself.

A cycle returns immutable status ALERT_EMITTED / NO_ALERT / ERROR, evaluated
(whether Tonight returned a valid result), UTC logical_time, Tonight status,
reason codes and optional internal OpportunityAlert. ALERT_EMITTED means an
atomic ledger claim, not notification delivery. Policy disabled returns
NO_ALERT/alerts_disabled without evaluating Tonight or touching the ledger.
Forecast unavailable and thrown Tonight errors return ERROR; ordinary Tonight
refusals (including missing availability) return NO_ALERT via existing guards.
Invalid time returns ERROR without I/O. Errors contain stable phase codes, not
exception messages or user data. A claim failure never resets the ledger.

Cadence is a separate pure value: a required positive timedelta, is_due(time,
last_cycle_time) and next_due(last_cycle_time), all using injected aware times.
Equality is due; earlier times are not due. No clock, sleeping, scheduling,
implicit cadence state or catch-up loop. The caller invokes run_cycle only when
due and owns cycle timing state. Errors consume no runner scheduling state.

Repeated evaluations may produce new decision identities; the existing ledger
family cooldown still suppresses them. Exact opportunities remain permanently
deduplicated, including after cooldown. A new opportunity after cooldown may
claim. Rebuilding a runner with the same durable ledger preserves suppression.
The ledger is the sole atomic authority, including concurrent calls. No retry
on claim failure: a write might already have committed. Claimed alerts are not
a delivery outbox; a crash after claim can lose a future delivery (at-most-once).

No scheduler integration, daemon, notification, webhook, Field Lab or NAS
changes. Operational weather/profile acquisition and cadence persistence belong
to the next orchestration layer. Server policy remains disabled by default.
