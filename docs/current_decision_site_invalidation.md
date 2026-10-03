# Current decision and configured site

The current decision is a local Tonight result, valid only for the exact numeric
latitude/longitude and effective editor timezone captured when it was received.
The fingerprint excludes name, Bortle, equipment and global profile revision.
Changing coordinates or the trimmed effective timezone clears the decision and
its fingerprint, the selected observation execution, and the recent catalogue.
Returning to the previous site does not resurrect the decision. Accepted mission
invalidation keeps its existing configuration rules.

The immediate observation context requires this fingerprint and, when loaded,
matching `weather_trust.requested_latitude`, `requested_longitude` and timezone.
Missing fingerprint, incomplete loaded coordinates or mismatch fail closed.
No provider fetch or automatic Tonight calculation is performed. A site generation
also rejects an in-flight Tonight response across A -> B -> A.

The availability screen explains that Tonight must be recalculated for immediate
observations. Its explicit recent-decision entry opens an editor with no decision
ID. The existing catalogue uses the exact current coordinates; only explicit
selection supplies a persisted ID. The existing canonical lookup, confirmation,
timezone behavior and stale catalogue response guards remain in use. No historical
timezone is invented and no persistent site identity is introduced.

Configuration changes block an already open editor through its frozen anchor.
Draft and pending contexts, payloads, UUIDs, storage keys, global locks and recovery
journal are preserved. A catalogue opening never silently adopts an old pending
ID. Existing reconciliation/recovery remains responsible for its own envelope.

Same-origin tabs publish `astropilot.decisionSite` after configuration initialization.
A different site signal (or storage clear) invalidates the receiver synchronously,
clears its accepted mission and rereads only `/v1/configuration`. A generation
rejects superseded configuration reads; read failure leaves the decision invalid and blocks Tonight and the catalogue until
a successful configuration reload.
Unrelated configuration updates with the same site fingerprint do not invalidate
current decisions. This covers changes made through the UI in tabs sharing origin
and localStorage. Direct external file/API edits, different origins, disabled
localStorage, or a frozen tab that has not yet received events are not a live
configuration notification mechanism; they require configuration reload. Loaded
weather coordinates still guard immediate observation context construction.

Validation uses the real JavaScript helpers in Node's existing browser simulator,
including two independent VM tabs sharing storage. This is a controlled simulator,
not a real-browser concurrency test. The regression covers immediate POST blocking,
non-geographic changes, A -> B -> A, same-name sites, timezone changes, loaded evidence
mismatch, explicit exact-site retrospective selection, untouched pending/recovery
artifacts, storage notifications and stale Tonight responses. Existing catalogue,
recovery, Outcome, configuration and recent-decision tests cover neighboring behavior.
