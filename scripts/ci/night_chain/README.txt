Night confirmation browser CI

Run automatically inside the existing Windows/Mac session-progress job. The full
Linux suite already covers Tonight API and UI helper contracts; this selection
adds real DOM + HTTP integration, not another copy of every API test.

Three fresh public profiles per OS: Hα, OIII, and site edit. The clock is frozen
at 2026-10-14 12:00 UTC and the fixed local availability is 2026-10-16 00:30–03:30
in Europe/Zurich, belonging to the requested night of October 15. Weather is a
validated clear fixture. Astronomy, thresholds, optical binding, decisions and
acceptance persistence use production code. No mission or legacy inventory is
fabricated. A recommended window is not acquired time.

Real browser interactions request recommendations, choose an intent and confirm,
or edit the latitude through the configuration form. Confirmations are replayed
through real HTTP with the same request id; a new app instance rereads the exact
persisted mission after server shutdown. Site edits clear the current decision
and send no old confirmation. All cases require no session or credit.

The common module isolates paths before product imports and denies non-loopback
Python connections. Chrome gets a new --user-data-dir for each case. Only on a
disposable Mac GitHub runner does its child process receive captured native HOME,
as required by the previously isolated Chrome network-service failure. Local
user HOME and application HOME are never restored by that override. Browser
protections are not disabled.

Chrome for Testing 155.0.8059.79 comes from its official immutable URL. Archive
SHA-256 values are pinned from the prior qualified Windows/Mac artifacts; a
mismatch fails. Provenance records the binary hash, checked-out source SHA and
PR head (which can differ from the tested synthetic merge SHA). Unsupported
platform/architecture combinations fail rather than selecting a personal browser.

Python 3.12 + locked test dependencies and Node with built-in WebSocket are
provided by the existing job. Download, CDP, process and job deadlines are bounded.
Servers use a free loopback port and a fixture-only provenance endpoint to avoid
interacting with another local app. Each case owns a separate process group;
timeout cleanup targets that group/tree, not a generic browser/process name.

Artifacts include reports, screenshots, text and logs only, retained 14 days.
Actual application/browser profiles live outside the exported proof directory.
Successful cases require the server and browser processes to stop; an expired
case deadline fails the CI and invokes group/tree cleanup. Capture/network errors
remain distinct from failed product assertions in the logs. No live-weather,
installer, physical shutdown or concurrent NAS qualification is claimed.

The on-disk files in common.py are synthetic and disposable. No real Mac/Windows
profile is copied or uploaded. No change to business logic is made by this fixture.

Saved mission labels: after each Hα/OIII confirmation, reload the actual page,
assert its persisted option contains the target, recorded filter, both local
window endpoints and historical site zone, then reopen the same mission ID. No
new acceptance or write is allowed. The native session UI regression additionally
uses real API-persisted pairs with the same target/window, verifies each credit
(90/15 min), repeated discovery, midnight/DST/Winnipeg and unchanged canonical files.
Its DOM harness is distinct from these real-browser confirmation journeys.
