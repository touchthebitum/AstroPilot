# Current decision and configured site

The current decision is a local Tonight result, valid only for the exact numeric
latitude/longitude and effective editor timezone captured when it was received.
The fingerprint excludes name, Bortle, equipment and global profile revision.
Changing coordinates or the trimmed effective timezone clears the decision and
its fingerprint, the selected observation execution, and the recent catalogue.
Returning to the previous site does not resurrect the decision. Accepted mission
invalidation keeps its existing configuration rules. Active mission observation additionally
requires a numeric local acceptance generation and the exact current site fingerprint.
Persisted missions without that provenance remain available for historical consultation,
but cannot implicitly supply an immediate mission observation context; recalculate and
reselect for the current site, or use explicit historical decision/recovery selection.

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
clears its accepted mission and rereads only `/v1/configuration`. A common `configurationGeneration` is advanced before every ordinary load, storage
reload, save/update and configuration recovery/retry request, and when the installed
site changes. Each request captures its token before awaiting; only a response with
the current token can install configuration or update its result/error view.
`installCurrentConfiguration(payload, generation)` validates that token and alone
releases `decisionSiteReloadRequired` after successful initialization. The initializer
itself never releases the blockade. Failure of the latest storage reload leaves
Tonight and the catalogue blocked; an older successful load/save/recovery cannot
unblock them. A subsequent relevant successful configuration response can.

The same-fingerprint storage shortcut is permitted only with no configuration request
in flight and no reload blockade. Every relevant notification while either exists
advances the generation and starts a new read, including A -> B -> A, A -> B -> C
and repeated identical signals. Superseded B responses cannot install B. The current
read must succeed before the blockade is removed. `configurationInFlightGeneration`
tracks the latest request; stale finally callbacks cannot clear a newer request.

Acceptance captures the common configuration generation, the site generation and
fingerprint, and the originating decision object/ID before sending. A valid server
confirmation received after any of these changes is retained in
`lastHistoricalAcceptance`, and its resolved acceptance attempt is cleared normally;
it does not assign an active mission, render it or open its modal. The backend's
canonical acceptance remains unchanged and can be discovered through saved missions.
A nominal acceptance stamps `acceptedSiteGeneration` and `acceptedSiteFingerprint`;
`observationContext('mission')` checks both defensively and fails closed on stale or
missing provenance. Saved-mission discovery captures the common generation and
configuration object, builds a local result and checks again after JSON awaits before
publishing it. Existing Tonight, recent decisions, Outcome and publication/recovery
locks retain their guards.
Unrelated configuration updates with the same site fingerprint do not invalidate
current decisions. This covers changes made through the UI in tabs sharing origin
and localStorage. Direct external file/API edits, different origins, disabled
localStorage, or a frozen tab that has not yet received events are not a live
configuration notification mechanism; they require configuration reload. Loaded
weather coordinates still guard immediate observation context construction. Tokens
order local UI responses, not backend transactions: a superseded save/recovery may
still complete on the server. A later explicit reload is required to learn external
or late server state. Historical mission payloads do not prove current geographic
lineage, so the UI does not manufacture local acceptance provenance for them.

Validation uses the real JavaScript helpers in Node's existing browser simulator,
including two independent VM tabs sharing storage. This is a controlled simulator,
not a real-browser concurrency test. The regression covers immediate POST blocking,
non-geographic changes, A -> B -> A, same-name sites, timezone changes, loaded evidence
mismatch, explicit exact-site retrospective selection, untouched pending/recovery
artifacts, storage notifications and stale Tonight responses. Existing catalogue,
recovery, Outcome, configuration and recent-decision tests cover neighboring behavior.

The async regression harness also executes production load/save/recovery, storage
reload, acceptance and saved-mission functions with deferred responses, including
failure followed by stale success, ABA/ABC/repeated notifications, a JSON await race,
nominal acceptance and stale/missing mission provenance. These are controlled Node
harnesses, not a claim of real-browser or server transaction ordering coverage.
