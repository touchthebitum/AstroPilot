# Guardian explicit renewal UI v1

The session panel reads `/v1/executions/{execution_id}/guardian-renewal` for the
selected exact execution. Configuration remains exclusively server controlled.
The disabled status hides the panel and preserves legacy transition payloads and
headers. An unavailable or invalid status prevents a start/stop transition rather
than guessing whether Guardian is enabled.

The explicit confirmation button is available for a fresh, owned, eligible
IN_PROGRESS execution. A visual-only interval reevaluates expiry using server
clock plus monotonic elapsed browser time. It performs no network request.

Each click submits exactly one UUID and the displayed instance guard. Pending
requests disable confirmation; only accepted server timestamps change the display.
Success, including replay, is followed by a status GET. Lost responses, timeout
and malformed or ambiguous results keep the uncertainty message visible and block
confirmation until the user explicitly checks status. This GET does not prove that
a particular command committed. There is no automatic retry or same-key retry UI.

Start and closure read status for their exact execution and add the adapter's
idempotency and owner headers when enabled. The existing single transition route
remains the only mutation route. Partial server failures distinguish execution
persistence from Guardian publication; orphan executions can still be closed.

Dynamic Node tests execute the production helpers through a deterministic DOM and
transport harness. The adapter integration suite independently checks the actual
FastAPI routes and single-transition dispatch. No weather, hardware, NAS, Field Lab
or Guardian recommendation policy is modified.

## Session closure latency audit (2026-10-10)

Base: `77516be4954d20ca5b40f598edf51d80248c2da7` (`origin/main`).
Investigation began before changing the production helpers. A deterministic Node
harness recorded the actual request order. The baseline stop path was:

1. GET mission sessions.
2. GET exact Guardian status (inside `reloadSessions`).
3. GET the same Guardian status (inside `guardianTransitionHeaders`).
4. One POST execution transition.
5. GET mission sessions.
6. GET exact Guardian status.

The redundant status GET was real, but did **not** explain the observed latency.
On the existing native Mac server, read-only measurements of five exact session
GETs took **3.85–4.94 s each**, versus **2.39–11.83 ms** for Guardian status GETs.
No commands or renewals were sent to that server. Its validation directory had
18 decision lineage files, about 137 MiB. Session projection calls `load_mission`
and `load_selection`; each of those previously deserialized **all** decision
lineage files. A list repeats these scans for each execution and for validated
credit provenance. The expensive work happens before and after the transition.

An isolated clone of the baseline and a temporary copy of the validation data
were then measured through the actual production service, file stores, FastAPI
middleware and routes. The full copied directory correctly failed validation:
some files use schema 11/12 and one contains an enum unsupported by this main.
Those files were excluded **only from the temporary benchmark copy**, yielding
six fully supported fixtures (about 31 MiB); no compatibility rule or original
file was changed. Thus this is a controlled bottleneck reproduction, not an
exact replay of the historical native 30-second click.

Instrumentation around `_load_all` found **13 complete lineage scans per mission
session GET**, accounting for more than 99% of its 5.26–5.93 s duration. The stop
POST took 6.53 ms. The baseline six-request stop sequence took about **11.68 s**
on this smaller compatible dataset. This proves the repeated-deserialization
bottleneck; it does not prove a hidden network timeout caused the original delay.

After the correction, the initial cold session read takes **615 ms**, including
one full validation scan. Unchanged subsequent session GETs take **4.21–21.01 ms**
and perform zero full lineage scans. The five-request stop sequence totals about
**48.60 ms**, including an 8.42 ms transition POST. These are single-run local
measurements, not performance SLAs. Large changed histories still require a cold
validation; contention and filesystem delays remain observable.

### Correction architecture and fail-closed boundaries

* Guardian-enabled session reads use a scoped provenance snapshot. Every request
  checks all JSON filenames and each file's device, inode, size, mtime_ns and
  ctime_ns under the existing directory lock. First use or any change decodes and
  validates every aggregate with the existing schema and consistency validators.
  A second signature check refuses changes during validation. A failed rebuild
  discards the old snapshot and returns 503. No schema errors are skipped.
* The persistent cache contains only encoded validated missions and immutable
  selections. Each mission lookup decodes its small mission document, preserving
  isolation and duplicate/missing-ID failures. Full decision payloads, execution
  states, profiles, credits, Guardian ownership and deadlines are not cached.
* The scoped service is used throughout the session list projection and credit
  validation. Outside Guardian the original lookup path remains in use.
* Start/stop skip the presentation-only Guardian read in their initial session
  reload, and creation reconciliation also skips it. The transition itself always
  reads fresh status for the exact execution immediately before its sole POST.
  Enabled mode supplies exactly `Idempotency-Key` and
  `X-Guardian-Owner-Instance-Id`; disabled mode supplies neither. An unavailable
  or malformed status blocks the POST even when an older snapshot showed a mode.
* After a write, sessions and Guardian are read again. A failed status preflight
  is not repeated during error recovery. Ambiguous writes are reconciled by GET,
  never replayed. Truncated successful response bodies retain write uncertainty.
  Pending explicit renewal prevents overlapping session commands.
* A canonical COMPLETED/INTERRUPTED session clears obsolete renewal messages and
  confirmation uncertainty, hides/disables confirmation and suppresses stale
  timestamps. If Guardian cannot be read, its status stays unknown; the UI does
  not invent an INACTIVE attestation. Publication failures remain visible in the
  separate session command message. Actual successful stop publication remains
  the unchanged lifecycle's authoritative INACTIVE write.

### Timeout and middleware audit

`readGuardianRenewal`, session inventory GETs and transition POSTs have no
application-level 15/30-second browser timeout. The 15-second abort belongs to the
explicit manual renewal command; it is not invoked by stop. The UI recovery,
observation, geolocation and alert timers are separate paths. Guardian HTTP weather
transport has its own bound but is not called by local session commands.
Middleware checks receipt time, content type and origin, then dispatches locally;
it does not fetch status, renew, retry or sleep. Adapter/lifecycle locks serialize
commands; persistent writer acquisition is nonblocking. Execution and provenance
file locks and filesystem operations can wait without a fixed 30-second deadline.
No timeout was shortened to hide the measured bottleneck.

For a future native trace, launch an **isolated** instance with
`ASTROPILOT_SESSION_TIMING=1` to enable `Server-Timing: session;dur=...` on session
and Guardian responses. In the browser console set
`globalThis.ASTROPILOT_SESSION_TIMING = true` and retain the network waterfall.
Console lines contain method, URL, elapsed fetch time, response status and server
time; they contain no request bodies. Browser timing ends at response headers,
while the network waterfall also exposes body/JSON time. Both switches are off
by default and neither introduces requests, aborts or background work. Capture
one explicit start, one explicit manual confirmation and one explicit stop.
This distinguishes backend processing from browser/network wait. Do not point a
main-schema reader at the incompatible native history or alter that history to
make the measurement pass.

### Validation

Dynamic production-JavaScript tests check exact GET/POST order, one transition,
headers in both modes, existing/new start, completed/interrupted stop, obsolete
message and timestamps, double clicks, renewal overlap, invalid/unavailable mode,
single failed preflight wait, lost/truncated responses, partial publication and
final status-read failure. Existing manual renewal/replay/expiry tests remain.
Persistent HTTP tests check start/renew/stop, an actual INACTIVE file, 15-minute
manual extension, timing opt-in, and absence of weather transport. Snapshot tests
check cold/hot scan counts, atomic replacement, corrupt/unrelated/removed files,
duplicate identities, concurrent changes, fresh execution/profile reads, unchanged
legacy projections, and refusal rather than reuse after invalidation.

All experiments ran in this chat's isolated checkout or temporary data copies.
The original checkout, `.DS_Store`, `astropilot.egg-info/`, local untracked files
and critical stash `223ec1f5904131d726b694655f137670c0ddeb0b` were not modified.
No hardware, silent renewal, merge or native live transition was performed.

Final validation: targeted checks **196 passed**, then expanded snapshot checks
**125 passed**. Full API/UI + Guardian + acceptance persistence suite:
**1206 passed, 3 Windows-native skips, 1 macOS-native test run separately**.
The macOS compilation test passed outside the sandbox without notification.
JavaScript syntax and diff whitespace checks passed.
