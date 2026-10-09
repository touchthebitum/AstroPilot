# Guardian explicit renewal API adapter v1

Implements the backend of
[the explicit renewal contract](../contracts/guardian_explicit_renewal_api_ui_v1.md).
No UI is wired. Confirmation remains solely a user assertion; no hardware,
weather provider, acquisition inference, Field Lab or NAS operation is involved.

## Activation and deployment

Default is disabled. Explicit activation requires both:

- `ASTROPILOT_GUARDIAN_EXPLICIT_RENEWAL=1`
- `ASTROPILOT_GUARDIAN_ATTESTATION_PATH=/absolute/path/to/session.json`

The path MUST be the same authoritative path as Guardian host configuration
`session_context.path`. The adapter resolves path aliases before opening its store
and its adjacent persistent `.writer.lock`. Missing/relative paths fail startup.
`create_app` also exposes equivalent explicit configuration arguments for embedding.

Deploy exactly one API worker, one deployment and one writer on a local filesystem
with reliable native advisory locking and atomic replacement. Disable worker pools,
auto-reload overlap and all standalone writers to this attestation path. Explicit
`WEB_CONCURRENCY` values other than `1` fail startup. A second adapter using the
same canonical path fails startup immediately; the OS lock is retained until
shutdown (in-flight commands complete first) or process death. Never delete,
replace or externally unlink the lock file. Advisory locking does not prevent an
uncooperative program from writing; prohibiting standalone writers is a deployment
requirement. A missing or unreliable lock implementation must prevent activation.

The existing launcher binds loopback. The API has no credential authentication or
CORS allowance; no new remote-access policy is introduced. JSON command requests
with a foreign browser Origin are rejected. If a deployment adds authentication,
keep its existing authentication and forged-request protections in front of these
routes; the instance ID is public concurrency metadata, never a credential.

## Transport

`GET /v1/executions/{execution_id}/guardian-renewal` provides the current instance
ID, exact execution status and current eligibility. It is read-only, even after
expiry, corruption or restart. Disabled mode returns an ineligible disabled status;
an unknown execution returns 404. Execution IDs follow the existing durable lineage
identity format (1–128 ASCII letters/digits/dot/underscore/hyphen, beginning with
an ASCII letter or digit).

`POST /v1/executions/{execution_id}/guardian-renewal` uses the strict JSON body and
UUID `Idempotency-Key` defined by the contract. Every response has `no-store`.

In enabled mode, the existing `POST /v1/execution-transitions` additionally requires:

- `Idempotency-Key: <UUID for this explicit action>`
- `X-Guardian-Owner-Instance-Id: <current startup instance ID>`

The existing transition body and successful execution response stay unchanged.
IN_PROGRESS calls lifecycle.start once. COMPLETED/INTERRUPTED call lifecycle.stop
once. Other domain transitions use the same journal/command lock and are rejected
while any execution is owned; they never publish an attestation. Fresh domain
transition rejections return sanitized 409 `guardian_execution_transition_rejected`;
a duplicate start while owned returns 409 `guardian_session_already_owned`.
Outside Guardian mode the original transition behavior and transport remain intact.
There are no UI changes, so the current UI cannot issue guarded commands when this
mode is enabled. Activation is for an explicit API caller until separate UI work.

## Ownership, journal and publication

Lifespan constructs one lifecycle with the real application service, one startup
UUID, one command RLock and a process-local journal (default 4096 admitted keys).
There is no credential identity in the current API; keys are scoped to this API
instance and carry command type, exact execution ID and normalized semantic body.
Reusing a key across commands or IDs conflicts. Terminal failures are retained as
well as successes. Capacity exhaustion rejects before mutation. Nothing is evicted
or restored across restart. A successful replay keeps the original deadline, marks
`replayed`, and changes only diagnostic server time; it never rewrites evidence.
An execution transition replay returns its original execution response.

Receipt time is captured by middleware before body handling or lock waiting. Renew
checks authoritative execution and ACTIVE matching evidence at receipt and current
time. Its store validates again immediately before atomic replace, after temporary
file flush/fsync. Receipt age 900 seconds is accepted, 901 is rejected; future or
backward clocks fail closed. Out-of-order receipt timestamps cannot regress
published evidence. A prepublication validation rejection preserves existing bytes
and revokes eligibility where trusted state was lost. GET never revokes or purges.

Start/stop execution persistence and evidence publication are separate commits.
Known stale/conflict rejection reports `not_committed`; unproven persistence
outcomes report `unknown` and do not publish. A publication failure after successful
persistence reports `committed`/`failed`/`lost`, with no rollback. The lifecycle
attempts to remove last-good evidence on write failure; if removal also fails, an
independent reader can still see it until its original expiry. Subsequent renewals
cannot recover ownership. A new process rejects old instance guards even when the
file survives. An orphan execution can be explicitly closed, never reattached.

## Validation

`tests/guardian/test_guardian_renewal_api.py` covers strict requests, disabled mode,
startup exclusivity/configuration, guarded dispatch and no duplicate transitions,
renewal/replay/conflict/capacity, wrong owner and exact ID, missing/corrupt/mismatched/
future/expired/INACTIVE evidence, closed executions, delayed publication, clock
failure, 900-second boundary, out-of-order receipts, read-only GET, restart,
publication and removal failure, persistence uncertainty and concurrency rejection,
same-key HTTP concurrency and both renew/stop lock orders. Discarded successful
responses can be retrieved using the original key. Crash/restart invalidation is
covered without reclaiming surviving evidence. Native Windows locking requires the
Windows CI environment; no hardware tests are involved.
