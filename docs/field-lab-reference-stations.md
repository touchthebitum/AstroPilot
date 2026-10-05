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
checks. Existing endpoints and ancestors are compared by filesystem device/inode
identity, including the longest existing prefix of a destination to create.
This detects macOS case-insensitive aliases without relying on POSIX normcase.
Missing suffixes are compared conservatively with case folding from the deepest
shared real ancestor: potentially overlapping future case aliases are refused,
including on sensitive filesystems. Distinct existing directories remain distinct.
Identity lookup errors fail closed. Each operation rechecks configuration and both user roots. After resolving
the configured root, every directory component and the fixed `artifacts/`
subdirectory is opened relative to a pinned descriptor with `O_NOFOLLOW`.
Subdirectory/document symlinks and non-regular documents are refused. Replacing a path component with a symlink cannot redirect fd-relative publication.
This is not a guarantee against renaming an already opened directory.
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

## Local-process threat model: opened-directory rename

The supported boundary protects against configuration mistakes, path traversal,
case aliases and symlink redirection. It assumes no concurrent local process
with rights to rename directories in both the lab and user domains, and no
privileged process modifying these domains. Such processes are outside the
isolation guarantee: moving an opened `lab/artifacts` to
`user/field_observations` immediately before publication still allows the fd-relative
write there. User decoders continue to exclude the lab envelope.

The writer creates directories with mode 0700 and temporary files with mode 0600;
these modes are privacy defaults, not an enforced ownership/permission boundary.
Existing parents are neither recursively chmodded nor certified as a security
boundary. Checking owner/device/inode, retaining ancestor fds or revalidating
parentage before a write cannot eliminate a subsequent rename race. On this
same-user macOS/POSIX deployment, 0700 cannot remove the owner's rename rights.
A stronger guarantee would require a separately administered writer identity
and domain permissions, or a reviewed platform-specific backend. No such boundary
is implemented or claimed here. The deterministic rename regression intentionally
records successful relocation/publication and subsequent decoder exclusion; it
must not be interpreted as a race-prevention test.

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
Additive lab observations/evaluations retain `field_lab_document_excluded`
diagnostics without making the snapshot incomplete; HTTP 200 and statistics of
valid user evidence are preserved. Missing observations referenced by evaluations,
and excluded required forecast/execution/decision joins, remain blocking with
`missing_user_observation` or `expected_user_document_excluded` diagnostics.
An excluded file at a 64-hex user evaluation identity is conservatively treated
as a lost/ambiguous user proof unless its name is the lab idempotency-key hash.
Thus arbitrary additional lab files with user-shaped evaluation identities can
still suspend statistics; there is no trusted historical manifest to distinguish
all additions from replacements. Likewise an unreferenced removed evaluation
cannot in general be reconstructed from surviving files. The contract does not
claim to detect every past deletion or deliberate replacement with a lab hash.
Diagnostics/fingerprints may reflect extra files; valid user data is unchanged.

## Prerequisites for the next lot

Offline tests cover disjoint roots, both overlap directions, default-root
protection, symlink aliases and redirection, traversal, missing configuration,
capability failures, immutable/idempotent publication, digest validation,
calibration exclusion, all user decoders and user history/statistics preservation.
Review this lot read-only and merge it before any station integration. Subsequent
station code must construct only the dedicated lab model/store and preserve this
boundary; it must not reuse user application factories or publish lab artifacts
into user sessions, profiles or histories.
