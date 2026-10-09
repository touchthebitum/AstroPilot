# Guardian scheduler persistence v1

Opt-in `GuardianScheduler(state_store=GuardianSchedulerStateStore(data_dir))`.
The caller supplies a dedicated Guardian owner/context data directory; the adapter
uses only its `guardian_scheduler/` child. No user-profile or alert-ledger lookup.
Omitting the store preserves #349's explicitly in-memory API and guarantee.
All persistent schedulers for one owner MUST share this directory and cadence.

Schema 1 in `guardian_scheduler/state.json`: exact keys `schema_version`,
`cadence` (UTC anchor and integer interval_seconds), `last_reserved_slot`,
`last_completed_slot`; timestamps are canonical aware UTC ISO strings or null.
No decisions, observations, assessments, credentials or business state persist.
Cadence mismatch fails closed, preventing reinterpretation of an old watermark.

A stable `.lock` file uses POSIX flock LOCK_EX|LOCK_NB or Windows byte locking
LK_NBLCK. Contention returns SKIPPED/state_locked immediately. The lock covers
read/check/atomic durable claim, the entire runner cycle, and completion, preserving
#349 anti-overlap across processes even when the current slot changes. OS releases
it after process death; never unlink the lock file. Local filesystems only.

Missing state means clean initialization. Invalid JSON, duplicate/extra keys,
unsupported schema, noncanonical timestamps, inconsistent or off-cadence watermarks,
and I/O errors return ERROR/state_error with no runner invocation if claim fails.
Never reset corrupt state. Recovery requires explicit operator repair from trusted
state; no automatic repair, retry, catch-up or stale-reservation expiry.

Claim first durably advances last_reserved_slot, retaining last_completed_slot.
Slots <= reserved are SKIPPED/slot_already_reserved. Only after a successful claim
may GuardianPeriodicRunner.run_cycle run. Successful validated non-ERROR cycles
atomically advance completed. Exceptions/ERROR/invalid results retain the claim;
process-control exceptions propagate and release the lock. Crash after claim,
before/during/after evaluation or before completion loses that slot conservatively.
No replay; future current slots remain executable when state is healthy. Completion
write failure returns ERROR/state_error, possibly after evaluation, and retains the
reservation. Completed means evaluated, never permission for downstream action.

Each write uses a unique temp in the dedicated directory, flush + file fsync,
atomic replace, and POSIX directory fsync. Before replace canonical state survives
partial writes; after replace/fsync failure the runner is not started for a claim.
Temps are cleaned on handled errors; crash leftovers are ignored. The guarantee
assumes intact local filesystem state and OS durability semantics. Deleting state,
changing directory/owner, filesystem loss or rollback can defeat idempotence.
No transactional downstream delivery, exactly-once effects, persistent host,
notifications, hardware, Field Lab or NAS integration is provided.
