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
