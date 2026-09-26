# NightMerit / AstroPilot 1.0.0-beta.7 release notes

Status: local release preparation. Beta.7 has not been packaged, tagged, or
published by this increment. These notes describe the 18 PRs merged after the
`v1.0.0-beta.6` tag, through source baseline
`8410e7f6e33099beb7dcb1070b5e7f108885f3b7`.

## What changed since beta.6

### Intent progress and project completion

- Project progress can be reviewed and edited per acquisition intent.
- Remaining work is derived per intent and used when evaluating candidates.
- Completed intent targets are excluded from recommendations.
- Completed projects from legacy profiles are also excluded, preventing old
  project state from re-entering the active candidate set.

### Persistent sessions, executions, and audited credits

- Mission execution sessions and their state persist across reloads.
- Progress is credited through an explicit audited ledger tied to contributing
  sessions, rather than inferred from an unaudited total.
- Corrupt, conflicting, or incomplete saved credit lineage is rejected instead
  of silently changing project progress.
- Historical sessions and mission progress are restored, including multiple
  contributing sessions, while invalid duration state is cleared between
  executions.

### Explainable refusals and actionability

- Intent eligibility refusals are exposed as structured assessments.
- Recommendations explain why a mission is not actionable instead of reducing
  the result to a generic refusal.
- Productivity diagnostics distinguish usable, rejected, and unavailable time,
  with invariants that keep the breakdown consistent.
- Weather-provider caution can coexist with intent eligibility; caution does
  not masquerade as a categorical refusal.

### Weather, cloud sampling, midnight, and DST

- Hourly cloud values are sampled correctly across quarter-hour slices.
- Weather reliability language now describes the actual evidence and preserves
  intentional caution while provider history is still immature.
- Fixed availability windows roll over midnight correctly.
- Elapsed-time calculations in the core night pipeline use UTC-safe arithmetic
  across daylight-saving transitions.
- Season sampling and productivity presentation use the same elapsed-time-safe
  semantics, avoiding DST-related label and duration drift.

### NightMerit UI and clearer configuration language

- The application now presents **NightMerit** as its user-facing product name.
- Acquisition-intent wording is separated from physical hardware-filter
  wording so users are not asked to interpret the two concepts as identical.
- Legacy filter inventories are treated as non-authoritative. They remain
  available for historical compatibility but do not silently constrain the
  current intent/filter decision path.

## Compatibility and identity contract

Beta.7 preserves historical decision data through current persistence schema
v9 and compatibility readers for schemas v1-v8. Existing beta profiles and
their established data locations must continue to upgrade in place.

For that reason, **NightMerit is the visible application name, while the
technical and distributed identity remains AstroPilot for beta.7**. The release
continues to use:

- `AstroPilot.app` and `AstroPilot.exe`;
- the AstroPilot installer and its existing application identity;
- bundle ID `fr.astropilot.desktop`;
- the existing AstroPilot data and log paths;
- Python package `astropilot`.

No executable, application bundle, installer identity, bundle ID, package, or
technical path is renamed in beta.7. This is an intentional upgrade-safety
contract, not incomplete UI branding.

## Known limitations and remaining release gates

- Windows packaging is unsigned. Testers must expect the platform warning;
  signing is not claimed for beta.7.
- Native macOS and Windows artifacts must still be produced from one reviewed
  release commit and validated on their target platforms.
- macOS signing/notarization and Windows install, launch, upgrade, uninstall,
  reinstall, persistence, and runtime-identity checks remain mandatory gates.
- Dynamic UI tests and final artifact checksums must be recorded before a tag
  or GitHub Release is considered.

See [the release checklist](release_checklist.md) for the authoritative gates.
