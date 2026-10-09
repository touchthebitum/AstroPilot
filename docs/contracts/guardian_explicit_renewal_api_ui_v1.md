# Guardian explicit renewal API/UI contract v1

Status: proposed production integration contract; no endpoint, UI wiring or
activation is implemented by this change. Implementers MUST satisfy this contract
before enabling it. MUST and MUST NOT are normative requirements.

Manual renewal means only: **the user confirms that acquisition continues at the
instant the API receives their explicit confirmation**. NightMerit does not
technically verify acquisition. Neither an IN_PROGRESS record nor API availability
proves that acquisition continues.

## Existing architecture and integration boundary

Baseline: `main == origin/main == e2858b771305b1bd83d7bdd2d2363ef89548d2b6`.
The current path is `sessionCommand → startSession/closeSession` in
`astropilot/web/app.js` → `POST /v1/execution-transitions` in
`astropilot/app.py` → `DurableTonightApplicationService.transition_execution` →
`ExecutionOutcomeApplicationService.transition_execution` → validated persistent
replacement with expected prior execution → UI reread. The command declares a
start or closure; it neither starts nor observes hardware acquisition.

`astropilot/guardian_session_lifecycle.py` already provides explicit start, renew
and stop, a process-local owner and an RLock. `GuardianSessionStore` publishes
atomic local attestations; its reader accepts age in [0, 900] seconds. Neither is
currently wired to these UI/API commands. The scheduler owns assessment cycles,
not acquisition. See [lifecycle writer](guardian_session_lifecycle_writer_v1.md),
[session context](guardian_active_session_reliable_v1.md) and
[Guardian API](guardian_api_v1.md).

## Activation and exclusive ownership

Production configuration MUST explicitly opt into manual Guardian renewal. Default
is disabled. UI presence, saved IN_PROGRESS history or configured weather providers
MUST NOT enable it. Disabled mode keeps existing execution commands and offers no
renewal action; renewal requests return 409 `guardian_mode_disabled`.

One API process MUST construct exactly one `GuardianSessionLifecycle` with the
real execution service and the same authoritative absolute attestation path read
by Guardian. Only one execution may be owned. All start, renew and stop commands
and their idempotency records MUST use one command lock around that instance.
The existing lifecycle lock alone does not protect an HTTP adapter's cache.

V1 supports one worker, one deployment and one writer for this path. Activation
MUST fail startup if exclusive writer ownership cannot be established; deployments
must prohibit parallel workers, overlapping reload processes, standalone writers
and other instances using the path. A deployment lock must have process-lifetime
ownership. A random API instance ID is generated at startup and never restored.
The instance ID is a concurrency guard, not authentication or a secret.

In Guardian mode, IN_PROGRESS commands MUST call `lifecycle.start` once; COMPLETED
or INTERRUPTED commands MUST call `lifecycle.stop` once. The handler MUST NOT also
call the execution transition service directly. Any alternative mutation entry
point must obey this dispatch boundary. Other transitions MUST NOT attest activity;
while owned, reject commands that could bypass the lifecycle's closure semantics.
Stop remains available after ownership loss/restart to explicitly close an exact
execution through the real service. UNCONFIRMED does not attest stopped acquisition.

## Proposed renewal request

`POST /v1/executions/{execution_id}/guardian-renewal`

Content-Type: application/json. Required `Idempotency-Key` header is a fresh UUID
for each user action. Exact JSON body (no additional fields):

```json
{
  "schema_version": "guardian-explicit-renewal-v1",
  "confirmation": "USER_CONFIRMS_ACQUISITION_CONTINUES",
  "owner_instance_id": "opaque-current-api-instance-id"
}
```

The path identifies an exact execution, never the latest execution for a mission.
No client timestamp, TTL, state, provenance, policy or hardware fields are accepted.
The handler captures a timezone-aware UTC receipt timestamp before waiting for the
command lock. It supplies that timestamp to `renew(observed_at=...)`. A duplicate
uses the original timestamp. Queueing or slow writes MUST NOT extend it.

Under the command lock, validate current ownership, exact ID, stored ACTIVE
attestation for that ID and authoritative IN_PROGRESS execution. Both receipt and
commit-time clock checks MUST reject future or expired evidence, and a receipt
older than 900 seconds by publication time MUST NOT be published as successful.
A backward clock jump or invalid server clock makes renewal unavailable. Age 900
is valid; age greater than 900 is expired. Validate freshness with the current
server time, not only the receipt time. Subsequent Guardian reads independently
apply freshness; publication cannot grant extra time.

The successful write uses the existing envelope: version
`guardian-live-session-v1`, source `caller_session_heartbeat_v1`, provenance
`CALLER_ASSERTED`, state ACTIVE, session_id equal to execution_id. Receipt time is
its observed_at. Renew does not transition execution or amend acquisition history.

## HTTP results and error schema

All responses MUST use `Cache-Control: no-store`. Current server_time is UTC with
Z. Success is 200 only after attestation publication succeeds:

```json
{
  "schema_version": "guardian-explicit-renewal-v1",
  "execution_id": "execution-id",
  "owner_instance_id": "opaque-current-api-instance-id",
  "confirmation_kind": "USER_ASSERTION",
  "confirmed_at": "2026-10-09T16:00:00Z",
  "expires_at": "2026-10-09T16:15:00Z",
  "server_time": "2026-10-09T16:00:00Z",
  "replayed": false
}
```

A sanitized error has schema_version, code, execution_id (or null if invalid),
server_time, execution_commit (`not_attempted`, `committed`, `not_committed`,
`unknown`), guardian_publication (`not_attempted`, `failed`, `unknown`) and
ownership (`retained`, `lost`, `unknown`). No filesystem paths, raw exceptions,
weather data or favorable Guardian assessment are returned. Renewal always has
execution_commit `not_attempted`.

| HTTP | Code and meaning |
| --- | --- |
| 422 | `invalid_guardian_renewal_request`: invalid path/body/header, extra fields or missing explicit confirmation; no mutation |
| 409 | `guardian_mode_disabled`: opt-in absent |
| 404 | `execution_not_found`: exact execution absent; no fallback |
| 409 | `guardian_owner_instance_mismatch`: old process or stale page |
| 409 | `guardian_session_not_owned`: ID is not this instance's owner |
| 409 | `guardian_execution_not_in_progress`: authoritative execution is closed or otherwise ineligible |
| 409 | `guardian_session_attestation_lost`: absent, unreadable, corrupt, UNKNOWN, INACTIVE, future, expired or mismatched attestation |
| 409 | `guardian_confirmation_expired`: receipt became too old before publication |
| 409 | `guardian_idempotency_conflict`: same key with different semantic request |
| 503 | `guardian_attestation_publication_failed`: write failed; ownership revoked |
| 503 | `guardian_execution_persistence_failed`: start/stop execution persistence failed or outcome uncertain |
| 503 | `guardian_clock_unavailable` or `guardian_state_unavailable`: trusted validation cannot complete; no renewal |
| 500 | `guardian_command_failed`: unexpected failure; outcome must be marked unknown unless proven |

Use existing authentication/access policy; this proposal adds no remote-access
permission. If credentials are used, the adapter must prevent cross-origin forged
commands under that policy. An error MUST never imply acquisition is stopped or
Guardian is synchronized. Validation errors write nothing. A wrong request ID or
old instance guard must not revoke an unrelated healthy owner. Loss of the actual
owner's attestation, execution eligibility or trusted state revokes its eligibility.

## Idempotency and concurrency

The future adapter MUST keep a bounded process-local command journal, scoped by
instance, authenticated caller where applicable, command type, exact execution ID
and key. Store the normalized request fingerprint and terminal result inside the
same command lock. Admit keys before any mutation; when capacity is exhausted,
return 503 `guardian_command_capacity_exhausted` before mutation. Retain records
for the whole instance lifetime; never evict and re-execute a previously admitted
key. Restart discards the journal and ownership and changes the instance guard.

Same key and same semantic request returns the original result without calling
start/renew/stop again and without rewriting evidence. A replayed success has the
original confirmed_at/expires_at, `replayed: true` and current server_time. It is a
receipt of a past command, NOT a claim of current eligibility. Read current status
to display present ownership/freshness. Never resurrect an expired attestation from
a cached success. Same key with changed body/path/command returns 409. Concurrent
identical requests produce exactly one mutation; a fresh key requires a new click.
Do not automatically retry a terminal publication failure with a new key.

Start/stop MUST use the same journal protocol, requiring key and current instance
guard in Guardian mode; exact transport additions to execution-transitions remain
future work. Existing domain transition rejection remains authoritative for fresh
keys. A replay must not execute a second transition.

Serialize different-key renewals and stop/start across the same boundary. A renew
that wins the lock may publish; a subsequent stop writes INACTIVE. If stop wins,
renew fails. Receipt timestamps must not regress evidence: reject a later lock
acquisition with an earlier receipt as 409 `guardian_confirmation_out_of_order`.
Execution service concurrency checks remain required. External execution changes
cannot justify renewal; exclusivity is a prerequisite, not distributed arbitration.

## Persistence and partial failure

Start/stop persist the execution first, then publish Guardian evidence. These writes
are NOT one transaction. On execution failure, do not publish and do not claim a
transition; if commit outcome cannot be proven, report unknown and require a
read-only authoritative reread. On publication failure after a persisted transition,
return 503 with execution_commit `committed`, guardian_publication `failed`,
ownership `lost`. Never undo a committed execution to manufacture consistency.

Lifecycle publication failures revoke ownership and attempt removal of old evidence.
Removal failure is also surfaced, sanitized. If write AND removal fail, a last-good
file can survive until its ORIGINAL expiry. Do not promise immediate fail-closed
behavior to an independent reader during that filesystem failure. The API refuses
all subsequent renewals; UI shows synchronization unavailable. Existing Guardian
reads still expire the surviving file at its original deadline and never refresh it.

The current library does not implement the journal, instance guard, HTTP mapping,
commit-time checks or cross-process deployment lock. Those are future adapter
requirements. Its existing write/remove limitations must remain visible.

## Read-only status and client uncertainty

A future read-only `GET /v1/executions/{execution_id}/guardian-renewal` returns exact
execution status, guardian_mode_enabled, owner_instance_id, owned_here,
confirmation_kind (`USER_ASSERTION` or null), confirmed_at/expires_at (nullable),
server_time, renewal_eligible and a sanitized ineligibility reason. Eligibility is
computed from current owner + ACTIVE fresh attestation + IN_PROGRESS execution.
Expired/missing/corrupt evidence means ineligible; never synthesize a timestamp.
Mode disabled returns a disabled status; unknown execution returns 404. This GET,
all other GETs, polling and UI rendering MUST NOT write evidence, reclaim ownership,
change executions, or purge files. Polling is informational only.

Timeout, dropped response or client disconnect means outcome unknown to the client;
it does not cancel a server mutation. Show uncertainty immediately. A user-requested
retry may reuse the SAME key/body/instance guard to retrieve the original result;
never mint a new key automatically. A GET can establish current state, but is not
proof that a particular key committed. Restart makes the old guard invalid and
renewal fails closed even if a fresh attestation survives. Server crashes between
publication and journal recording cannot be replayed as a new confirmation after
restart. Only another explicit start of an eligible new execution can establish
ownership. No reattachment of historical IN_PROGRESS, recovery endpoint or implicit
start is allowed. An orphan IN_PROGRESS execution can be explicitly closed first.

## User interface

When opt-in is active, show an explicit button with this exact label:
**Je confirme que l’acquisition est toujours en cours**.

Adjacent explanation: “Cette confirmation vient de vous. NightMerit ne vérifie pas
techniquement que l’acquisition continue.” Show last accepted server confirmation,
the deadline (15 minutes), freshness/ownership status and the limit after restart
or expiry. State that Guardian actions remain recommendations, not hardware control.
A display countdown may use server_time plus elapsed client time for presentation;
server validation is authoritative and the countdown must never invoke renewal.

Enable the button only for a currently eligible exact execution. Each deliberate
click generates one new key and uses the displayed current instance guard. Disable
while pending. Do not extend the displayed deadline optimistically. On success,
show the returned confirmation/deadline; on replay, preserve that original deadline
and reread current status. On timeout or ambiguous error show “Résultat incertain —
vérifiez l’état avant de confirmer à nouveau.” On partial start/stop failure show
execution persistence separately from Guardian synchronization. On lost ownership
or expiry disable renewal and explain that a new explicit session is required;
provide explicit closure of the old execution where valid.

No silent renewal timer, browser heartbeat, focus handler, reconnect handler,
background task, service availability check or polling callback may renew.
Start is a user declaration; stop is an explicit user closure. None proves hardware
state. Hiding the tab, losing the network or leaving the API running has no positive
meaning for acquisition freshness.

## Preserved boundaries

No hardware control or inferred acquisition from weather, ASIAIR, browser presence,
processes, network, NAS or IN_PROGRESS history. Guardian risk/action rules,
Open-Meteo selection and requests, Field Lab and NAS behavior are unchanged.
Attestation loss uses existing UNKNOWN/fail-closed recommendation behavior; it
must not improve risk/action or retain favorable cached context. Renewal never
calls weather providers or changes Guardian policy. Opt-in grants no unattended
acquisition authority.

## Acceptance scenarios before production wiring

Existing lifecycle characterization tests cover publication, expiry and restart.
The additional tests accompanying this document exercise wrong IDs, corrupt and
mismatched attestations, non-IN_PROGRESS state and read-only behavior without
implementing the proposed HTTP interface. They do not certify an HTTP adapter.

Future integration tests MUST demonstrate:

1. Disabled defaults; rejected unsafe multi-worker/writer activation; one lifecycle
   shared by all command routes; start/stop perform exactly one domain transition.
2. Strict request/response schemas, server receipt clock, boundary 900/901 seconds,
   delayed requests, backward clocks and out-of-order concurrent receipts.
3. Every rejection in the HTTP table; no mutation on GET or invalid requests;
   no ownership recovery from restart, expiry, cached response or history.
4. Same-key duplicate/retry/concurrency executes once; changed payload conflicts;
   capacity rejection precedes mutation; replay after expiry/stop does not renew;
   old-instance retry after restart rejects.
5. Deterministic renew/stop races in both lock orders; execution concurrency errors;
   persistence failure, commit uncertainty, publication failure after commit and
   double filesystem failure with surviving evidence only until original expiry.
6. Response loss after commit, disconnect and crash before journal completion;
   truthful client uncertainty and user-requested same-key retry.
7. Exact button copy, visible deadline/limit, no optimistic success, explicit opt-in,
   expiry/restart disabled state, zero renewal from timers/polling/reconnect/focus.
8. No changed risk/action rules, provider calls, Field Lab/NAS writes or hardware
   commands. Existing Guardian test suites continue to pass.
