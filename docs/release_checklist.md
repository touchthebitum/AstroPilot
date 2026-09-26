# Release checklist: 1.0.0-beta.7

Canonical project version: `1.0.0b7`. Tester label: `1.0.0-beta.7`.
Future tag: `v1.0.0-beta.7` (not created by release preparation).
Comparison baseline: existing tag `v1.0.0-beta.6`.

## Release-preparation record

- [x] Confirm baseline before editing: `main == origin/main` at
  `8410e7f6e33099beb7dcb1070b5e7f108885f3b7`, with no tracked changes and only
  `.DS_Store` untracked.
- [x] Confirm critical stash
  `223ec1f5904131d726b694655f137670c0ddeb0b` is intact.
- [x] Review the 18 merged PRs after `v1.0.0-beta.6` (#267 through #284) and
  capture their tester-facing delta in [the beta.7 notes](release_notes_beta7.md).
- [x] Set the canonical version and version-dependent contracts to `1.0.0b7`.
- [x] Preserve the transitional NightMerit/AstroPilot identity contract.
- [ ] Record the final release-preparation commit after review.

## Local validation for the preparation change

- [x] `uv lock --check` passes with 49 packages resolved.
- [x] 117 targeted version, runtime identity, UI asset, macOS packaging, and
  Windows installer contract tests pass.
- [x] Python byte-compilation smoke validation passes for `astropilot`,
  `decision`, `astro_score.py`, and `scripts`.
- [x] `git diff --check` passes.

These local checks validate release preparation only. They do not certify a
native package, installability, upgrade behavior, signing, or publication.

## Transitional branding contract

NightMerit is the name visible to users in the application. For beta.7, the
technical and distributed identity remains AstroPilot: `AstroPilot.app`,
`AstroPilot.exe`, the AstroPilot installer, bundle ID `fr.astropilot.desktop`,
the existing AstroPilot data and log paths, and Python package `astropilot`.
Do not rename these artifacts, identifiers, packages, or paths in beta.7. This
deliberate split preserves upgrades and existing beta profiles.

## Native release gates (not performed by this increment)

- [ ] Confirm a clean tree, `main == origin/main`, and the same final release
  commit on both build hosts before either build.
- [ ] Build the macOS arm64 application and ZIP from that commit; sign,
  notarize, staple, inspect archive contents, extract, and verify Gatekeeper
  and signature.
- [ ] Build the Windows x86_64 onedir application and per-user installer from
  the same commit. Windows output remains unsigned for beta.7; document the
  warning shown to testers.
- [ ] Validate installed runtime identity, launch, persistence, beta.6-to-beta.7
  profile upgrade, uninstall, and reinstall on clean/native macOS and Windows
  accounts. Run the dynamic UI suite where Node is available.
- [ ] Record actual artifact names and SHA-256 checksums.
- [ ] Review all gates and only then create `v1.0.0-beta.7` and consider a
  GitHub Release. Neither step belongs to release preparation.

Expected filenames from the current build scripts, **not existing artifacts**:
`AstroPilot-1.0.0-beta.7-macos-arm64.zip` and
`AstroPilot-1.0.0b7-windows-x86_64-setup.exe`.

## Scope guard

This increment performs no packaging, native build, tag, GitHub Release, or
push. No previous artifact or checksum may be repurposed as a beta.7 build.
