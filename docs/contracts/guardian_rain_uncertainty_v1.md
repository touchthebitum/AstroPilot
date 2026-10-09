# Guardian rain uncertainty v1

Immutable GuardianRainUncertainty (a GuardianEvidence subtype in the required
rain_eta_minutes channel of GuardianObservation) separates
current rain evidence and rain_eta_minutes (existing channels) from optional
forecast interval samples and probability. Each GuardianRainInterval records
aware start/end, optional rain_mm and probability_percent (0..100). These are
interval sums/probabilities, never current-rain booleans or exact onset times.
The evidence has version guardian-rain-uncertainty-v1, source, provenance FORECAST
or OBSERVATION, and aware timestamp. All values are retained for inspection.

Allowlist: open_meteo_current_v1 and open_meteo_intervals_v1 identify MISSING ETA
only, with FORECAST provenance. caller_onset_v1 supports ONSET_CAPABLE or MISSING
with either provenance; the caller must attest an exact onset-capable source.
No provider in production currently supplies such an onset. ONSET_CAPABLE requires
a valid numeric rain_eta_minutes channel; a None value is not an onset.
MISSING, invalid capability, malformed/future/stale metadata, invalid intervals
or unsupported source/version makes completeness false and risk UNKNOWN. All
observed hazards, including rain_active:CRITICAL, remain in reasons. UNKNOWN
retains the existing more precautionary EMERGENCY_STOP recommendation; current
rain with complete valid evidence remains CRITICAL/STOP_SESSION. No change to
#345 precaution ordering, even when live current rain is true but ETA is missing.

Explicit current false never establishes no imminent rain. Positive or zero
interval/probability signals never improve or escalate classification, and no
new probability/interval threshold is introduced. Future forecast start/end is
permitted; metadata timestamp itself must be fresh and nonfuture. Intervals
must be ordered and non-overlapping; source freshness uses existing policy.
Deleting rain uncertainty removes the required ETA channel and yields UNKNOWN.
The subtype keeps uncertainty and onset in one evidence item, so dropping
uncertainty cannot expose an underlying favorable ETA.

Compatibility: with legacy plain GuardianEvidence, guardian-v1 explicit GuardianEvidence(None,
...) in the ETA channel continues to mean an affirmative no-imminent-rain
assertion, not an unavailable ETA. A legacy numeric ETA remains an explicit
caller onset assertion; adapters must never fill it from interval sums or
probability. Missing channel remains UNKNOWN. The production
adapter always leaves the ETA value None and supplies the typed MISSING evidence. Open-Meteo
current rain/showers retain #352 modeled-current semantics. Forecast payloads
are not newly requested or parsed in v1; typed interval evidence is caller-
injected through the domain model only. No API/UI/transport request changes.
