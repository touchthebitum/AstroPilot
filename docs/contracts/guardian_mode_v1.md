# Guardian Mode v1 — guardian-v1

Pure injected domain/decision service. No session authorization, engine rerun,
I/O, scheduler, hardware, notification, Tonight, Opportunity Alerts or Field Lab
integration. CONTINUE means no additional Guardian stop recommendation; it never
permits starting a session. Inactive sessions retain diagnostic recommendations;
hardware_action is always absent.

Observation, assessment and recommendation are separate immutable objects.
Every channel carries source identity, explicit provenance, timestamp and value.
Only OBSERVATION or FORECAST with nonempty source and aware, nonfuture timestamp
within max_age_seconds is trusted. Legacy/unknown, absent, malformed or stale
critical evidence produces UNKNOWN, never SAFE. All six channels are required:
rain_active, rain_eta_minutes (None explicitly means no imminent rain), wind_kmh,
gust_kmh, humidity_percent, dew_spread_c. Missing dew spread is not computed.
Caller supplies aware now and session_active; no system clock is consulted.

Versioned policy thresholds are explicit scenario defaults, not calibrated
scientific or equipment limits: rain imminence <=15 minutes; wind watch/warning/
critical >=15/25/35 km/h; gust >=20/30/40 km/h; humidity >=85/90/95 percent.
Dew spread <=5/3/1 C maps WATCH/WARNING/CRITICAL, reusing boundaries from
 decision/quality/dew_risk_engine.py (inclusive boundaries are conservative).
Freshness <=900 seconds is provisional. Users may tighten thresholds.

SAFE→CONTINUE, WATCH→MONITOR, WARNING→PREPARE_STOP,
CRITICAL→STOP_SESSION, UNKNOWN→EMERGENCY_STOP. UNKNOWN is epistemic uncertainty,
not a measured hazard, but ranks above CRITICAL in precaution ordering. This
ensures deleting any evidence cannot improve level/action, including deleting
known rain. UNKNOWN includes all still observable hazard reasons. EMERGENCY_STOP
is a recommendation only. Evidence completeness means all required channels are
valid/trusted/fresh. decision_eligible means complete evidence for classification;
it is never permission to observe or execute hardware actions.

Rain ETA is relative to its source timestamp: elapsed minutes reduce ETA;
an elapsed ETA stays CRITICAL until new evidence supersedes it.
Active rain or near rain is CRITICAL. Any channel may independently escalate;
maximum precaution wins, no additive scoring. Assessment includes stable ordered
reasons, per-channel source timestamps/provenance, policy version and completeness.
No hysteresis or remembered state; outputs deterministic for identical inputs.
Next integration must preserve this boundary and validate equipment-specific
thresholds before any operational safety use.
