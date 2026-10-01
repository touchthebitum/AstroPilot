# Field Validation / Outcome History v1

`GET /v1/outcome-evaluations/history` is the only new HTTP route. It reads persisted comparisons. It never evaluates, saves, repairs, quarantines or acquires a writer lock.

## Query contract

| Parameter | Default | Validation / meaning |
| --- | --- | --- |
| `observed_from`, `observed_to` | absent | Inclusive endpoints; ISO 8601 timezone-aware UTC (`Z` or `+00:00`). No local times. From must not exceed to. |
| `latitude`, `longitude` | absent | Supply both, finite latitude −90…90 / longitude −180…180. Exact requested coordinates, no rounding or nearby-site grouping. |
| `provider` | absent | Exact provider ID from a comparable result's `forecast_point`. Evidence providers do not qualify. |
| `variable` | absent | `temperature_c`, `relative_humidity_percent`, `wind_speed_kmh`, `cloud_cover_percent`. |
| `mode` | absent | `decision_only` or `execution`. |
| `status` | absent | `comparable`, `partial`, `not_comparable`; comparison coverage, never assessment. |
| `include_superseded` | false | Allow superseded rows in consultation; always exclude them from statistics. |
| `limit` | 50 | Integer 1…100. |
| `cursor` | absent | Opaque continuation; reuse the same filters and limit. |

A provider/variable filter selects evaluations having a matching result (when both are provided, the same result must match both). Retained rows and their descriptive statistics keep all persisted variable results. Thus a provider filter is not a provider-specific score or an attribution of the other variable results. Each result retains its own provider. Global coverage describes the original evaluation, including partial evaluations.

## Response

- `rows`: page of enriched persisted evaluations. Includes evaluation/comparison/decision/observation/execution IDs, algorithm versions, policy parameters, original computed time, observed UTC time (nullable), mode, coverage status, results with forecast and observed values/categories and persisted errors, reasons, observation provenance and quality, assessment and outcome evidence in detail. Includes exact `site` or null, canonical `context`, `compared_providers`, separate `evidence_providers`, `unknown_dimensions` with reasons, result-level unknown provider/model reasons, `supersession` (`active`, `superseded`, `indeterminate`), `lineage_reasons`, `admissible`, `sources_coherent`, `statistics_eligible`, `exclusion_reasons`.
- `next_cursor`: nullable continuation for the next page.
- `dataset_fingerprint`: SHA-256 covering content of every Outcome and FieldObservation final JSON document, membership of both directories, referenced forecast evidence, execution and decision lineage documents, including missing/unreadable markers. Foreign decision lineage files are not searched. All observations are scanned, even without Outcomes or outside filters.
- `view_token`: SHA-256 over the dataset fingerprint, canonical filters (including limit) and fixed history policy.
- `statistics`: full filtered admissible active population, independent of page, or null when suspended.
- `diagnostics`: individual document kinds/IDs and public reason codes, without filesystem paths, document contents or exception details. Includes excluded incompatible versions/policies, duplicate admissible outcomes, invalid lineage and unknown observed dates excluded by a date filter.
- `completeness`: `complete` or `degraded` (reading failed partially or changed during the scan).
- `certification`: `certified` or `statistics_suspended`; this certifies the admitted population's integrity, never scientific independence, forecast quality, sufficiency or photo success.
- `readable_filtered_rows`: consultation count only; never presented as active population N in degraded reads.
- `policy`: strict version/policy allowlist and descriptive-only metadata.
- `filters`: canonical effective filters.

Ordering: `observed_at_utc DESC`, `observation_id ASC`, `evaluation_id ASC`. Unknown observed dates are last, never replaced by computed time. They are excluded with diagnostics when a date filter is present.

## Certification and corruption

Every filename/join identity is validated with the existing domain identity validators before constructing a path. Invalid identities and excessive JSON nesting are isolated as document diagnostics. Per-file decoding reuses canonical deserializers. Inventory, decoding and fingerprint checks open root/family directories with `O_NOFOLLOW`; document reads use no-follow stat, reject non-regular objects before opening, then use `O_NOFOLLOW | O_NONBLOCK` and verify regular-file type and device/inode on the opened descriptor. Symlinks, directories, sockets and FIFOs are isolated as unreadable document diagnostics without reading their content; required documents suspend certification. Metadata is collected without following links. Unused foreign joins are fingerprinted but never decoded or used for certification. Corruption/unreadability is isolated and consultation continues with HTTP 200, diagnostics and suspended statistics. A missing required join also degrades the snapshot. An absent unused directory is a legitimate empty dataset. An inaccessible directory returns HTTP 503 (`outcome_history_unavailable`). Unexpected internal errors remain server errors, never silently empty history.

Source coherence is explicitly checked against the persisted comparison `source_digest`, using the exact canonical observation/evidence digest contract without comparing or evaluating again. Each comparable persisted result must also match its canonical observation exactly (normalized numeric value or cloud category) and a canonical evidence point by variable, unit, value, provider, model, retrieval/valid time and temporal offset. All provenance fields available in the persisted result are checked; requested/grid coordinates exist only in evidence and are covered by the canonical source digest. No forecast selection or comparison engine is invoked. Divergence emits `outcome_history_observed_source_mismatch` or `outcome_history_forecast_source_mismatch`, retains the row with unknown source dimensions, and suspends active population statistics even when only one variable differs. Unverified forecast provenance cannot populate the provider filter. Missing or divergent source digests make date/site unknown and rows ineligible. Unknown requested site coordinates also suspend certification. Decision-only target/model dimensions may remain explicitly unknown without preventing descriptive forecast statistics.

Supersession is determined over all FieldObservations before filters. Cycle detection memoizes visited ancestors and is linear in the observation graph. Connected lineage components with a cycle, fork, absent parent, changed decision or changed execution are indeterminate. An Outcome inconsistent with its observation is also indeterminate. Indeterminate lineage or multiple admissible v1 evaluations for an observation suspends population statistics conservatively. No latest-by-time selection is performed. Superseded evaluations are never eligible for statistics, even when displayed.

Allowlist: persistence schema 1 / domain `outcome_evaluation.v1`; evaluation algorithm `outcome_evaluation.v1`; comparison `forecast_observation.v1`; scope `decision_attached_evidence`; exact default baseline policies: `nearest_forecast_utc.v1`, 30-minute offset, UTC, nearest per variable, no interpolation/averaging; `cloud_mapping.v1` with 10/25/50/80 percent boundaries; canonical variable units. Incompatible readable evaluations are diagnostic rows excluded from statistics. Unsupported persistence versions are excluded documents with diagnostics. Malformed documents, including unparseable policy values, degrade certification.

## Pagination and errors

The cursor is an opaque URL-safe encoded continuation containing fingerprint, view token and offset. Consumers must not construct it. The v1 token is not authenticated: a client can alter a valid offset while keeping dataset/view tokens. This known P3 remains deferred; the cursor is not an authorization boundary. Invalid cursor/filter → HTTP 422 (`invalid_outcome_history_cursor` / `invalid_outcome_history_filters`, or FastAPI type-validation detail). Changed dataset between pages → HTTP 409 `outcome_history_dataset_changed`; reload from the first page. Filter/limit changes invalidate a cursor with HTTP 422. All five document families are inventoried before decoding, with membership, no-follow metadata and content hashes (including foreign corrupt files). Every decoded/joined content is checked against that initial manifest. After all decoding and join reads, a final content-hash pass is followed by complete membership and metadata revalidation; this also detects changes to files already hashed earlier in the final pass. Any detected instability returns HTTP 409 `outcome_history_dataset_changed`, with or without cursor, with no success rows or statistics. This is a snapshot validated by passes, not a promise of perfect atomicity; a mutation after final validation or restored between checks may escape detection. No persistent snapshot or lock is created.

## Descriptive statistics

Only individually evaluated observations contribute. No reconstructed nights or independence claims.

- N admissible evaluations/observations, distinct non-null decision IDs and execution IDs.
- Original coverage counts: comparable, partial, not comparable.
- Per variable comparable/non-comparable/absent counts; N comparable observations and distinct decision/execution IDs.
- Temperature: mean persisted signed error (forecast − observed) and mean absolute error in °C; humidity errors in percentage points (`error_unit: percentage_points`, source `unit: %`); wind in km/h. Means use scaled finite summation to avoid overflow of finite inputs. A nonfinite aggregate suspends statistics with a diagnostic while preserving consultation rows. Empty means are null. Partial evaluations contribute their comparable variables.
- Clouds: forecast × observed category count matrix, N comparable, match/mismatch counts.
- Reason code counts of distinct affected observations, deduplicated across global and variable reasons.

The assessment is only expandable detail labeled “Suffisance des éléments d’évaluation”. There is no ranking, global score, provider score, recommendation, threshold change, calibration or learning. The known PR #294 Compare-button P3 is unchanged.

UI: independent request generation invalidates responses on filter input, navigation, close/cancel and reload. A dataset conflict clears continuation and asks for reload. Unknown context/site/provider/model is explicit; output uses text nodes, including persisted strings.
