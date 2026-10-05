# Reference Weather Station Field Lab: prerequisite isolation

This micro-lot provides offline storage primitives only. **No station collection
may begin until this isolation lot has been merged and reviewed.** MeteoSwiss
clients, STAC/CSV ingestion, forecasts, comparisons, reporting, scheduling,
calibration and UI are outside this change.

## Filesystem boundary

`FileFieldLabStore()` is the dedicated API. It accepts no arbitrary directory
argument and has no fallback to any user store. Set `FIELD_LAB_DATA_DIR` to an
explicit absolute root. Missing configuration, relative paths and any `..`
component are rejected before storage creation. The resolved root must be
strictly disjoint from both the effective `ASTROPILOT_DATA_DIR` root and the
platform's default user root: equality and ancestry in either direction are
rejected. In particular, `<ASTROPILOT_DATA_DIR>/field_lab/` is **not allowed**.
A separate sibling root is suitable.

Paths are expanded and canonicalized (including symlink aliases) before overlap
checks. Each operation rechecks configuration and both user roots. After resolving
the configured root, every directory component and the fixed `artifacts/`
subdirectory is opened relative to a pinned descriptor with `O_NOFOLLOW`.
Subdirectory/document symlinks and non-regular documents are refused. Directory
swaps cannot redirect a subsequent path-based publication into user storage.
An existing unmarked root must be empty before initialization: the API will not
claim a directory already containing arbitrary user documents. The root owns an immutable `.field_lab_namespace` marker with namespace and
schema version; readers reject a missing or incompatible marker on an existing
root. Unsupported secure filesystem capabilities, including Windows, fail
closed before any filesystem mutation. This deliberately follows Outcome
History's POSIX capability policy; Windows support needs a separately reviewed
secure backend, not a less secure fallback.

User observation, evaluation, forecast evidence, execution and lineage stores
check their directory on each access. They refuse overlap with the configured
lab root and refuse directories with a lab marker in their ancestry, including
resolved aliases. Outcome History checks both its root and each inspected
subdirectory; Recent Decisions uses that same boundary. Configuration and
namespace markers are application boundaries, not an OS permission system:
operators must preserve markers and use these APIs rather than manually
rewriting storage domains. Arbitrary custom user store locations outside the
normal effective/default roots must also be kept disjoint from the lab.

## Artifact and provenance boundary

`FieldLabArtifact` is a separate frozen model, not a user `FieldObservation`.
Every artifact carries `artifact_type`, `schema_version=1`,
`namespace=provenance=field_lab_reference_station`, `created_at_utc` (UTC only),
`source_id`, `idempotency_key`, JSON object payload and its SHA-256 digest.
Payloads are copied into immutable canonical JSON. The model and decoder reject
any other namespace/provenance/version, duplicate JSON fields and any
`calibration_eligible` value other than the boolean `false`. User models and
existing user calibration eligibility semantics remain unchanged. Lab objects
cannot enter the typed user store writer APIs.

Publication uses a flushed and fsynced temporary followed by an atomic,
create-only hard link and directory fsync. Final artifacts are immutable. The
validated idempotency key determines a SHA-256 filename: an identical rerun
returns `False`; reuse with a different envelope raises a conflict. The caller
must reuse the original UTC creation time for a rerun. Reads check envelope,
identity and payload digest; they never acquire a writer lock or create files.
There is no collection/network activity in either operation.

## Defense in depth for user readers

All six user persistence decoders explicitly reject lab namespace/provenance
markers, including nested observation `source_type`. Outcome History skips such
files with `field_lab_document_excluded` diagnostics before joining them into
observations/evaluations. Recent Decisions rejects them through its evidence
decoder. Malformed/incompatible documents continue to follow the existing
reader diagnostics. Accidentally copied lab files therefore cannot contribute
to user history rows, recent decisions or statistics, even in a user directory.
Diagnostics/fingerprints may reflect the extra file; valid user data is unchanged.

## Prerequisites for the next lot

Offline tests cover disjoint roots, both overlap directions, default-root
protection, symlink aliases and redirection, traversal, missing configuration,
capability failures, immutable/idempotent publication, digest validation,
calibration exclusion, all user decoders and user history/statistics preservation.
Review this lot read-only and merge it before any station integration. Subsequent
station code must construct only the dedicated lab model/store and preserve this
boundary; it must not reuse user application factories or publish lab artifacts
into user sessions, profiles or histories.
