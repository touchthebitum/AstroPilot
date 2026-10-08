# Opportunity Alerts v1: durable suppression ledger

Baseline: PR #331, main `3b0522374350808a3ebec4601bbcf1692ad29a0e`.

## Responsibility and placement

`astropilot.opportunity_alert_ledger.FileOpportunityAlertLedger(directory=None)`
implements the internal `OpportunityAlertLedger` protocol. Inject it into
`OpportunityAlertService`; the in-memory adapter remains available for tests.
Default directory: `get_user_data_dir()` (including `ASTROPILOT_DATA_DIR`).
Dedicated files: `opportunity_alert_ledger.json` and
`.opportunity_alert_ledger.lock`. One directory belongs to one user.
No profile loading, profile migration, transport, scheduler or notification is
introduced. No Field Lab dependency. There is no automatic production wiring
because there is no alert transport or scheduler yet.

## Schema 1

The root has exactly `schema_version: 1`, `latest_logical_time` (UTC ISO timestamp
or null), `entries`, and `families`. Each entry is indexed by the existing alert
key and contains only `family_key`, `last_emitted` (UTC logical timestamp), and
`policy_version: 1`. `families` maps each family key to its latest emitted logical
timestamp, checked against the entries on every read.

The existing hashes are unchanged: family includes project, imaging field,
intent, site and filter profile; exact key additionally includes window,
decision and selection lineage. Policy is provenance, never part of the key.
No weather, score, mission payload or recalculated business data is persisted.
`latest_logical_time` persists the existing global monotonic guard, including
forward claims refused for duplicate/cooldown. Exact keys are retained forever;
only a new exact key can emit after family cooldown expires. Different families
are independent except for the existing global logical-time guard.

## Claim transaction and failures

The existing cross-platform `exclusive_file_lock` combines a per-path thread
lock and OS lock (POSIX flock / Windows msvcrt). A separate stable lock file
covers read, schema validation, suppression check and write. Every claim reloads
canonical state under that lock; there is no process-local durable cache.

Writes use a unique temporary file in the same directory, flush and fsync,
then `os.replace`. POSIX also fsyncs the directory. ALERT can be returned only
after the committed claim completes. Corrupt/unsupported schema, policy,
inconsistent family indexes and timestamps fail closed with an explicit
`OpportunityAlertLedgerError`; storage/locking errors do likewise. The service
propagates the error and returns no alert. Corrupt files are never reset,
quarantined or repaired automatically. Missing canonical file means an empty
ledger. Temporary files are never treated as canonical state.

Policy schema 1 is the only currently supported version. Any future version
requires a deliberate compatibility change; unknown incoming or stored policy
versions block emission. Changing supported v1 policy settings preserves all
exact-key suppression and applies the caller's current cooldown, matching #331.
No implicit reset occurs on a policy change.

Only admissible live Tonight results reach claim. Missing ledger does not scan
or replay history; historical/legacy results still cannot emit.

## Limits and recovery

This provides durable at-most-once claims, not exactly-once notification delivery.
A crash after commit and before returning ALERT can lose an alert, conservatively,
while preventing its duplication. An error after replacement may similarly leave
a committed suppression claim. Windows follows the repository's existing atomic
replace/file-fsync pattern; POSIX additionally syncs the directory. Locks assume
a local filesystem and cooperating writers, not distributed/NAS storage.

Deleting the canonical ledger intentionally loses suppression history, since
absence must mean empty. Logical inconsistencies are detected, but this is not
cryptographic protection against a valid-looking edited file. Manual recovery
must preserve known claims and provenance; there is no automatic recovery tool.
Exact-key retention grows unbounded, as in the memory adapter. Do not prune
without a separately reviewed retention contract. Next step: alert API transport
with explicit error reporting and delivery semantics.
