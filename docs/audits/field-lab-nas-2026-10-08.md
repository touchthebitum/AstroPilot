# NAS dataset audit — 2026-10-08

Verdict: **USABLE_WITH_GAPS**, for offline weather matching only.

Read-only SMB input `/Volumes/Docker/nightmerit-field-lab/data`, corresponding
NAS store `/share/Docker/nightmerit-field-lab/data`; NAS currently 192.168.0.11.
Frozen file-list snapshot: 10,531 JSON artifacts (10,769,664 bytes) and 10,531
matching metadata files (4,949,681 bytes). Artifact sizes range from 443 to
253,336 bytes (median 764 bytes). Collector remained running; this is
not an atomic NAS snapshot. Local copies only, no input mutation.

Created range: 2026-10-07 15:00 UTC through 2026-10-08 17:30:40.849468 UTC.
Two UTC dates, about 26.5 hours; 26 success attestations and 27 log entries
(including one no-op). One unattested hourly slot: 2026-10-08 09:00 UTC.
This does not prove absent collection: measurements for that period exist.
Zero empty/unreadable/invalid JSON, payload digest failures, metadata identity
mismatches, duplicate file contents, duplicate idempotency keys, or missing
outer provenance fields. Zero naive/invalid timestamps in outer creation,
observation/retrieval and forecast target samples/full relevant records.
Schemas: envelope v1; stable payload key shapes per type, sampled chronologically
at beginning, middle and end for every artifact type. No in-place normalization.

Types/counts: acquisition 3726; observation 2862; comparison 1548;
comparison_state 1872; official_asset_activation 325; collection_success 26;
forecast/seal/seal_completion/seal_commit 36 each; report 26; catalogue and
catalog_activation_event 1 each. These are not independent scientific samples.
Logical repetition across acquisitions/observations: 3726 extra records for
2862 measurement facts; acquisition provenance must survive deduplication.
Unique observation quality: 2808 unverified, 54 missing (1.89%). Official QC
is unknown, not verified. Timestamp coverage comprises 2808 site/variable/time
slots over 5508 possible ten-minute slots: 2700 absent (49.02%). Mostly each
hour retains :50, :00, :10 from a rolling `now` asset. These are sampling gaps,
not evidence of a 49% scheduler failure. Observation range 2026-10-07 15:50
through 2026-10-08 17:10 UTC. Missing-valued facts remain distinct from absent
slots. All 12 sites have temperature, humidity and wind observations.

Sites: BAS BER CDF CHA DAV GVE JUN LUG NEU PAY SAE SIO.
Provider Open-Meteo, model `provider_default_unspecified`; observation source
MeteoSwiss. 36 station forecast runs, 24 hourly targets each, 3 variables
(2592 forecast values). Station coordinates/altitude/timezone, transport grid,
retrieval/code identity and prospective seal chain are available. Stored UTC
instants coexist coherently with station Europe/Zurich metadata.

Forecast-observation matching and provisional temperature/humidity errors are
possible, subject to seal-chain verification and unknown official QC. Wind
aggregation semantics are unverified; no wind error metric may be claimed.
No NightMerit outcomes/labels, filter OIII/Hα, lunar, transparency, seeing or AQI
evidence exists. False-positive/negative or filter calibration cannot be
inferred. Short duration and unspecified provider model prevent scientific
calibration conclusions. Reports are descriptive only, never production policy.

Next scientific step: review a longer unchanged collection window, stratify
by site and forecast lead time, investigate ten-minute sampling gaps, and
establish wind aggregation comparability before drawing bias conclusions.
