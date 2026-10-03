# Persisted recent decisions v1

`GET /v1/decisions/recent` is a bounded, read-only catalogue for a future explicit
retroactive observation selector. It does not evaluate Tonight, allocate IDs,
write documents, acquire writer locks, repair evidence or calculate scores.

## Query

- Required `latitude` and `longitude`: finite, within geographical bounds;
  match the exact requested coordinates in every evidence point. No radius,
  rounding, name matching or inferred historical site ID.
- Required `retrieved_from` and `retrieved_to`: timezone-aware ISO timestamps,
  normalized to UTC; inclusive, ordered, spanning at most 31 days. These filter
  forecast retrieval time, **not** observation or decision creation time.
- `limit`: default 10, range 1–50.
- `cursor`: signed opaque continuation, bound to filters, limit and evidence
  dataset fingerprint. Use unchanged filters. Invalid/tampered cursor: 422;
  changed dataset: 409 `recent_decisions_dataset_changed`, restart pagination.

## Response and provenance

`items` are ordered by retrieval time descending, then decision ID descending.
Every candidate has persisted valid evidence, one exact requested coordinate
pair and one unambiguous retrieval timestamp. No candidate is automatically
selected. `selectable_decision_only` only indicates usable evidence identity;
it does not promise comparability or authorize changing execution lineage.

Each item exposes the full `decision_id`, `retrieved_at_utc`, exact site
coordinates, forecast extent and supported variables. Creation timestamp,
site name/ID/revision/timezone, night date, decision status, supersession,
target and intent remain null: this first catalogue does not join acceptance
contexts, which do not cover all evidence documents. A client must never
present retrieval time or file modification time as decision creation time.

`time_basis` is `forecast_retrieved_at_utc`, `site_match` is
`exact_requested_coordinates`, and `comparability_guaranteed` is false.
Forecast extent may have holes and does not establish per-variable temporal
eligibility. OutcomeEvaluation remains the canonical comparison, including
inclusive ±30-minute selection and ambiguity handling.

Invalid, empty or inconsistent evidence is excluded with bounded diagnostics;
`complete` is false when any such document exists. No writes or quarantine.
An empty catalogue has `items: []` and `next_cursor: null`; it never triggers
Tonight. No observation or Outcome is reassociated by this endpoint.

## Storage and platform limits

The reader reuses Outcome History's hardened file read boundary: no symlink
following, regular files only, descriptor-relative opens and at most 16 MiB per
document. A scan permits at most 512 JSON documents and 32 MiB total accepted
content; exceeding either is HTTP 503 `recent_decisions_scan_limit` without a
partial page. These bounds apply to the entire evidence family, not merely the
requested time range. Narrowing the range cannot bypass the scan ceiling.
An indexed read-model would be needed for larger datasets.

Content fingerprinting uses file names and content hashes, not file dates.
Final evidence is immutable under the canonical store contract. An inventory
change during a scan yields 409. Pagination detects changes to any scanned
content. No stable snapshot is promised against noncanonical external editing
of existing files during a single request.

The existing History reader requires POSIX descriptor/no-follow capabilities.
Standard Windows therefore returns 503 `recent_decisions_unavailable` before
document access; no weaker fallback is added. A missing evidence family inside
an accessible root returns an empty page. An inaccessible/unsafe root or file
and oversized documents return redacted 503. Production reuses the existing
History cursor key; this GET never creates a key.

## Future UI boundary

Keep immediate capture unchanged. For retroactive capture, show human labels
with available date/site information and an ID suffix; confirm the choice
explicitly. Bind the observation draft to that choice without replacing the
current Tonight decision. Unknown metadata stays visibly unknown. A pending
payload retains its original ID, decision, execution and recovery entry.
Execution observations remain bound to the canonical mission/session decision;
the existing POST rejects inconsistent execution lineage. No silent selection,
correction, scoring or forecast recomputation is allowed.
