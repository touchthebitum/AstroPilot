# Archived session analyses

Computed analyses carrying a decision identifier from the production /v1/tonight path are
saved under the selected profile's analysis_history directory before the API
reports success. Each immutable record contains its decision identifier, UTC
creation instant, effective requested site/equipment/availability and validated
response transport. Forecast evidence remains in its existing independent store.
Reading history never invokes the decision service, weather, observation writes,
mission acceptance or alert claims. An archived result is not live authorization.

Mes analyses in the footer is available after restarting, including when the
current configuration cannot be read. Relire mes analyses is also available from
Mon historique. Dates use the archived forecast's site timezone when available;
otherwise UTC is explicitly shown. The view does not overwrite current decision,
selected project, or availability. It labels forecasts as historical.

A chosen target that cannot be evaluated retains a structured visibility
diagnostic. The altitude reason is emitted only when the same overlapping
window samples used by the existing engine are all below the configured minimum.
No samples, or any sample reaching the threshold, produces the conservative
target_window_unavailable reason instead. This changes explanations, not eligibility,
the minimum altitude, forecasting scores or mission authorization.
The no_candidate UI also renders existing structured rejection reasons.

Record schema: nightmerit.analysis_history.v1.
The catalogue is bounded to 512 records and 32 MiB, with at most 1 MiB per record.
No record is pruned automatically. Corruption, unsafe paths, conflicts, exhausted
limits or write failures are reported explicitly; existing files are not reset.
Files are published atomically and never overwritten. GET requests do not create
the directory or lock files. History GETs are paginated, read-only and no-store.

Profile backup includes analysis_history and validates every record on the
disposable validation copy. New archives containing this directory require a
version that understands it; older kits reject unknown files rather than omit
them. Existing isolated kits and profiles remain independent.

Old refusal responses were not saved by earlier kits. They are not invented or
reconstructed from current forecasts. In particular, installing this change
cannot recover the exact original M42 response from the October 25 private test.
Existing observations and comparisons are not migrated or rewritten.

Tests use synthetic records and weather only: original M42 time window through
the production engine/API, fresh-application reread, three unchanged sentinel
observations, unknown causes, immutability/limits/corruption, backup and restore.
The native Mac/Windows CI browser journeys additionally verify Simple/Pro at
390/1280 pixels, reload, historical-only viewing, inert stored text, request
failures and stale responses. They reuse the pinned Chrome for Testing already
installed by scripts/ci/night_chain/run.py; no npm dependency is added.
