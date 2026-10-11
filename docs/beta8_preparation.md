# AstroPilot beta 8 preparation — no builds performed

Canonical version: `1.0.0b8`. Targets: macOS ARM64 and Windows x86_64.
The MacBook Air remains the development reference. Changes are prepared in an
independent clone; the original working tree, index and security stash are not
inputs to any build job and must remain unchanged.

## Source provenance

The preparation starts at main commit
`bdc08659a8cf4e9946ae0abc825c647701cdb21c`. The published beta 7 tag
`v1.0.0-beta.7` points to commit `c47b2e6fe395f51678971d12a1cd451ba8aa9cfa`
(annotated tag object `ced77d5c36ed23f4f000fb8135dc590310c04fee`).
The beta 7 tag, historical release documents and stored TLS bundle are unchanged.

Main already includes Windows runtime/installer support, stale distribution
metadata cleanup, Windows Opportunity Alerts supervision, help UI, Guardian
renewal/lifecycle support, closure latency and saved mission timing corrections.
Do not cherry-pick those already merged changes again.

The 12 uncommitted files from the validated Air sources are reapplied as a patch,
without applying, moving or deleting the stash. They carry the strict certifi TLS
context, frozen macOS worker entry point and bounded output handling, both missing
macOS UI assets, live Tonight/NO_MISSION admissibility, contracts and regressions.
The imported patch is SHA-256
`1e7f1a68e8372e29b3a040173acdbb32ab81a5eec21c50860547dd131f853c41`.

Beta 8 additionally packages help.js and alert-status.js on Windows, updates the
canonical version and current-version contracts, and declares Matplotlib in the
packaging extra. Matplotlib and its dependencies are now resolved in uv.lock,
rather than installed outside the lock as during beta 7 macOS validation.
This dependency addition still needs build and regression validation.

## Build approval boundary

No final approved source SHA exists while these changes are uncommitted.
Do not use the base SHA above as the beta 8 candidate SHA.
After source review and explicit authorization, commit the prepared sources in
the independent clone, record the FULL 40-character SHA, and transfer or publish
that exact source commit through an authorized step. No push is authorized by
this preparation. Both platforms must use the SAME approved full SHA.

The manual workflow `.github/workflows/beta8-windows-manual.yml` has only a
workflow_dispatch trigger and contents:read permission. It uses pinned action
commits, a windows-2022 x86_64 runner, Python 3.13.5, uv 0.12.6, locked packaging
dependencies, and the runner's existing Inno Setup 6 compiler. It fails if tools,
version, lockfile, source identity or expected assets are missing. It uploads
candidate artifacts for 30 days; it does not sign, publish a release, or alter a
tag. The dispatched workflow's own SHA is recorded separately in provenance.
The workflow must be available for manual dispatch on an authorized repository
ref/default branch before it can be used. Do not dispatch it during preparation.

GitHub-hosted Windows Server 2022 is a build host, not Windows 11 qualification.
Runner images and Inno Setup can change; their versions are captured in the
provenance. Keep a durable verified copy of downloaded artifacts before retention
expires. Windows candidates are unsigned; do not claim Windows signing.

## Regression gates before building

- Review the full diff and exclusions; no real profiles, user databases, secrets,
  private certificates, virtual environments or previous build output may enter
  the source transfer or artifacts.
- Run the affected Guardian, Tonight, packaging, launcher, macOS application,
  runtime identity, integrated help, Opportunity Alerts and Windows installer
  suites in isolated environments after authorization. Existing beta 7 test
  results do not validate this beta 8 source tree.
- Run all supported Python 3.11/3.12/3.13 regressions as appropriate. The new
  packaging lock contains platform/Python markers and needs native resolution
  validation on both target platforms.

## macOS beta 8 gate

Use a NEW clean checkout/environment on the Mac mini in testastropilot-test,
at the approved full SHA. Confirm that SHA and version before dependency sync.
Use the locked packaging extra in .venv-packaging; do not inject extra packages
outside uv.lock. Clear signing environment variables for an unsigned validation
build. Build using scripts/build_macos.py only after separate build approval.
Never run release/build scripts in the conserved beta 7 artifact directory.

Expected identity: 1.0.0b8, approved SHA's seven-character runtime build label,
ARM64, bundle marketing version 1.0.0 and bundle build 8. Record the FULL source
SHA, lock hash, dependency/tool versions and binary hash separately.
Check UI assets and certifi/cacert.pem in the produced bundle. Re-run synthetic
Guardian and Opportunity Alerts cycles with a new isolated ASTROPILOT_DATA_DIR,
strict live TLS acquisition, interfaces, and native Quitter AstroPilot shutdown
(exit 0, port 8000 free). Check port availability before launch.
Do not reuse the beta 7 TLS bundle as the beta 8 artifact or as proof of beta 8.
Signing/notarization and signed-runtime revalidation are later separate gates.

## Windows 11 physical-PC gate

Frozen Windows Guardian acquisition now uses the packaged worker entry point,
a private bounded JSON response file, strict certifi TLS, an independent
PyInstaller child and CREATE_NO_WINDOW. Subprocess timeouts kill and reap the
child; temporary output is removed on all paths. This implementation has not yet
been tested on a native Windows bundle. Do not claim operational qualification
or feature parity before Windows 11 validation. Linux frozen acquisition remains
unsupported.

On a real Windows 11 x86_64 PC, use a separate local test account and synthetic
data. Verify downloaded SHA-256 values, provenance and approved source SHA.
Set ASTROPILOT_DATA_DIR explicitly to an isolated folder before every app launch.
Start Menu launch needs an isolated default test-account profile as it does not
inherit an arbitrary terminal environment variable; do not use a real account.
Check port 8000 before launch. Test both portable ZIP and per-user installer:
runtime identity, help UI, alert status, launch, persistence, clean shutdown,
installation, beta 7-to-8 upgrade with synthetic sentinel data, uninstall and
reinstall/data preservation. Cover paths with spaces and accented characters.
Opportunity Alerts notification/autostart checks must be isolated and opt-in;
remove only test registrations afterward. Check synthetic Guardian cycles and live strict HTTPS acquisition, certificate
rejection, timeout/reaping, private-output cleanup and absence of child UI/console.
Windows physical-PC results and new macOS results must both be recorded before
testers receive a candidate. No release publication is part of this workflow.

Before installer creation, the workflow scans the payload for user data, .env.*
files, private credentials and unexpected links; export repeats the scan. Only
_internal/certifi/cacert.pem is allowed as a PEM resource. The generated root
astropilot.egg-info directory is ignored; all other checkout cleanliness checks
remain active.
