# Field Lab Analyzer v1 contract

Offline/read-only tool: `python -m astropilot.field_lab_analyzer
{scan,normalize,report} --input RAW_STORE --output LOCAL_NEW_DIRECTORY`.
No network, production engines, Tonight, mission, actionability, ledger,
notifications, scheduler or collector imports. All dependencies are stdlib.
No production policy is written or applied. Reports contain findings only.

Pipeline: frozen sorted discovery -> strict JSON/envelope/digest/schema checks
-> canonical aware UTC/provenance -> logical measurement deduplication with
all source IDs retained -> normalized observations/forecast values -> exact or
unique nearest matching within configurable tolerance (default 10 minutes)
-> descriptive metrics and deterministic JSON/JSONL/Markdown local outputs.

Input symlinks/nonregular files and unknown schemas are rejected as evidence;
16 MiB per artifact cap. Unsupported artifact types are indexed, not interpreted.
Missing provenance invalidates evidence; naive/invalid timestamps are rejected.
No unknown field is converted into favorable evidence. `calibration_eligible`
must be false. Output must be new, outside the raw root and outside /Volumes
or /share; output symlinks/ancestors resolving into raw storage are refused.
Input marker and metadata are not required for a standalone artifact export;
raw artifacts are authoritative and metadata is checked in the NAS audit.

Versioned frozen models: SourceArtifact (relative path, byte SHA, identity,
kind, payload, status/issues); NormalizedObservation (site, source, variable,
UTC time, value/unit, quality, acquisition IDs); ForecastPoint (run/provider/
model, retrieval, seal evidence, target/value/unit); MatchedPair (forecast and
observation evidence, offset, signed error or null, reason/status/confidence);
MetricRecord (group/count/bias/MAE); ReportSummary (coverage/gaps/distributions/
counts/limits). Each serialized model carries schema_version=1.
Evidence IDs, confidence, status and priority are separate: evidence lists
retain provenance; confidence is unknown or unverified, never 'high'; status
explains comparability; priority is null unless explicitly supplied.

Duplicate acquisition/observation records are collapsed by full measurement
identity excluding retrieval and artifact type; all source IDs survive.
Conflicting revisions at the same time remain ambiguous (no optimistic choice).
Nearest equal-distance ties are non-comparable. Matching is within the same
site/variable/source/unit; no interpolation or unit conversion. Errors require
finite valid temperature/humidity values and unverified official observations,
a prospective forecast retrieved/created/sealed before both target and measured
time, and a valid forecast -> seal -> candidate -> commit identity/digest/time
chain. Wind, unknown variables, missing QC/values/seals and historical forecasts
remain non-comparable. Stored reports/comparisons never authorize new metrics.
Removing required evidence must not improve confidence or comparability for
a retained pair; metrics always publish eligible counts and exclusions.

Coverage gaps use the explicit ten-minute observation grid between each group's
first/last timestamps; hourly cycle gaps use success attestations. Neither
proves service failure. Horizon targets beyond available measurements stay
missing, not forecast failures. Report distributions contain count/missing/
min/max/mean by source/site/variable/unit; no quality score or favorable defaults.
Determinism applies to unchanged input bytes, file names and arguments; no wall
clock, absolute input path or output path enters artifacts. Live input additions
are excluded after discovery; immutable files must not change during reading.
Outputs: scan.json; observations.jsonl and forecasts.jsonl for normalize/report;
pairs.jsonl, report.json and report.md for report. Empty corpus is INSUFFICIENT.
The actual NAS audit precedes this contract; no collector/NAS code changes.
