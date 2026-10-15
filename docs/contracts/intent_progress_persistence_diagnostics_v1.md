# Intent progress profile persistence diagnostics v1

Scope: the profile saver invoked when applying an execution's intent progress
credit. OS errors from this saver become `IntentProgressPersistenceError`.
Read errors, other stores and programming/validation errors are outside this
boundary. Revision conflicts, corruption and credit eligibility retain their
existing codes and HTTP statuses. No schema, credit rule, lock, atomic write,
freshness, weather or retry behavior changes.

`POST /v1/executions/{id}/intent-progress-credit` returns HTTP 503 with
`detail.code=intent_progress_persistence_unavailable`, a bounded category and
a fixed message requiring session readback before retrying. Categories:
`permission_denied`, `storage_full`, `read_only_storage`, `quota_exceeded`,
`io_error`. No exception text or personal path is returned.
This means persistence could not be confirmed, **not** that rollback occurred:
a saver can replace the profile and then fail. Read the canonical session;
replay with the current profile revision returns `already_applied` if committed.
The UI reconciles state through its existing GETs, displays an explicit
unconfirmed-save message and does not automatically retry the write.

Every credit attempt gets a server-generated `X-Persistence-Diagnostic-ID`.
The success body remains unchanged; existing controlled refusals additionally
carry this header. Persistence failures and successful/applied or already-applied
results emit one `persistence_diagnostic ` JSON record to
`astropilot.launcher.persistence`, inherited by the existing rotating support log.
Eight fixed fields: schema_version=1, event, diagnostic_id, occurred_at_utc,
operation=intent_progress_credit, category, duration_ms, http_status.
Events: `intent_progress_persistence_failed` (503) and
`intent_progress_credit_result` (200). IDs are per request; no ambient mutable
request context or client-supplied identifiers are used. Business refusals do not
emit persistence-failure records. Profile, evidence/execution IDs, paths, URL,
exception text, credentials and payloads are omitted. No new log handler or data
directory is created. Diagnostic sink failures cannot change command results;
when storage also prevents logging, delivery of the diagnostic is not guaranteed.

Qualification injects denied/full/read-only/quota/I/O failures before real atomic
replacement, verifies byte preservation and temp cleanup, persistent correlation,
recovery and replay, plus failure after committed replacement without double
credit. Concurrent request IDs and broken logging sinks are covered. All data and
observations are synthetic, with independent temporary profiles on Windows/Mac.
