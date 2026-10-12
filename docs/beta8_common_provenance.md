# Beta8 common source provenance

The common source changes come from `AstroPilot-Beta8-Guardian-macOS-sources.zip`,
SHA-256 `893b8ef7ea96df5f1d157203b8337fcde0e8173f52e1c113319b3ace5a295f10`,
based on `bdc08659a8cf4e9946ae0abc825c647701cdb21c` plus uncommitted fixes.
The transferred macOS report, dated 11 October 2026, confirms that this source
archive was verified and built without subsequent source edits. Its native
arm64 validation binary has SHA-256
`c09bc11735893ee9c5f7103b741bc79b886ec173f1e685f8c6c10d2678505806`.
Both archive hashes were verified again on the Windows transfer drive.

Changes are replayed against `origin/main` at
`fdcd245750c919a26d970bcb7147d0797148582b`, preserving its Windows workflow.
The earlier Beta7 transfer patch is not a Beta8 source of authority and is not
applied. Archive omissions do not delete existing repository files.

The source scope is the portable Guardian dispatcher and bounded frozen HTTP
worker, complete web resources and reference catalog packaging, the explicit
strict injected-evidence option, the Tonight creation-refusal diagnostic,
persisted mission site timezone with schema-10-and-earlier reads, and canonical
`1.0.0b8` metadata. The Windows specification mirrors the verified macOS
specification. Existing associated Windows tests are carried forward, with
additional dispatch, frozen-failure, strict-evidence and alert refusal checks.
No Field Lab behavior, NAS integration, hardware control or alert authorization
rules change. Validation profiles, logs, build products and private data are
excluded from the source commit.

## NO_MISSION qualification

The follow-up diagnostic correction checks admissibility before live provenance:
the actual Tonight `NO_MISSION` result returns `NO_ALERT` with
`tonight_not_admissible`, without a ledger claim or an artificial live marker.
An admissible `AVAILABLE` result still requires the live marker and all existing
authority and evidence checks; without that marker it returns `NO_ALERT` with
`live_tonight_result_required`. Both paths have regression tests. This correction
changes refusal diagnostics only and was not part of the transferred Mac build.
The macOS report does not establish native Opportunity Alerts validation.

## Guardian review corrections

The injected-file provider now reads and validates one immutable payload per
cycle, sharing it between observations and session context. Previously an atomic
replacement between two reads could combine observations from one version with
the session state from another. A failed read clears the pending snapshot, so
later cycles cannot reuse prior evidence. A subsequent valid cycle can recover.
Duplicate JSON keys are rejected at every nesting level rather than accepting
the last value. Regressions reproduce the replacement race and ambiguous JSON
on the previous implementation and verify coherent, fail-closed behavior after
the correction. These changes are follow-ups to the transferred Mac sources;
they do not change the production weather provider or add execution authority.

## Validation boundary

Windows validation uses Python 3.12.14 and an isolated environment synchronized
from the transferred `uv.lock`. Tests isolate application data. Targeted
Guardian, packaging, persistence, Tonight, runtime identity and UI tests pass;
native POSIX checks are skipped and two symlink tests require a Windows
privilege unavailable on this machine. Windows alert supervision, notification
adapter (without sending), host/status and secure-filesystem fail-closed tests
also pass. The Beta8 wheel builds and its installed CLI smoke test preserves
its fictitious profile and filters.

The exhaustive Windows suite is compared against unchanged `origin/main`.
It is not wholly green: existing tests assume POSIX secure storage, symlink
privileges or platform-specific JavaScript invocation. Those unrelated failures
are reported separately; they do not justify relaxing storage safeguards.
The transferred native macOS validation is distinct from these Windows tests.
The macOS binary was signed ad hoc, without notarization or confirmed Gatekeeper
acceptance. No release, tag, publication or merge is performed here.

## macOS transport follow-up — 12 October 2026

PR #368 is already merged into main at
`fd891c92c2145a43b03cf0045638e29bd3331d99`. Its web-resource packaging,
portable dispatcher and NO_MISSION refusal checks are retained.

Two remaining corrections come from the local Mac checkout and the independently
prepared Beta8 commit `59d00b7e92ef3430b07a23f55608d61c78047bb3`.
The HTTP worker matches that commit byte for byte. It explicitly uses certifi's
CA bundle with certificate and hostname verification enabled; certifi is now a
direct locked runtime dependency. The frozen macOS transport receives bounded
JSON via a private temporary file because a windowed executable has no Python
stdout. The child resets the PyInstaller environment and is still killed and
reaped on timeout. The Windows/Linux stdout path and Windows CREATE_NO_WINDOW
flag from main are preserved; the older Mac-only refusal of frozen Windows is
not replayed.

These fixes have a separate provenance from the transferred MacBook Air build
based on bdc0865. The archived Mac-mini reports describe HTTPS-worker validation
of the 59d00b7 preparation; those reports are supporting evidence, not a claim
that the new common branch has native Windows validation or Apple notarization.
No application data, validation profiles, binaries or test logs are committed.
