# Release checklist: 1.0.0-beta.6

Canonical project version: `1.0.0b6`. Tester label: `1.0.0-beta.6`.
Future tag: `v1.0.0-beta.6` (not created in this versioning run).
Historical tag `v1.0.0-beta.5` exists. The beta.3 checksums and native
validation remain in the [historical closed-beta record](closed_beta.md).

## Local versioning candidate

- [x] Ultimate beta.6 release gate reported **PRÊT POUR VERSIONNAGE BETA.6**
  on source HEAD `80e7d9bb8d973df86523394e54b88cad5f22bf7b`.
- [x] Review version bump, UI label, notes, and local checks in this run:
  `uv lock --check`, 140 targeted tests, 3332 full-suite tests (44 warnings),
  JavaScript syntax, Python compilation, and `git diff --check` passed.
- [x] Commit the reviewed versioning change: `b642342abb080aa412f3cb12058e7b9fda75fc00`.
- [ ] Confirm a clean tree, `main == origin/main`, and the same final release
  commit on both build hosts before either build.
- [ ] Build the macOS arm64 ZIP from that commit, then sign, notarize, staple,
  inspect archive contents, extract, and verify Gatekeeper and signature.
- [ ] Build the Windows x86_64 onedir application and per-user installer from
  that same commit; verify installed runtime identity and update behavior.
- [ ] Record actual artifact names and SHA-256 checksums (none for beta.6 yet).
- [ ] Validate installation, launch, persistence, and upgrade on clean/native
  macOS and Windows accounts. Rerun relevant platform test suites.
- [ ] Review all gates and only then create `v1.0.0-beta.6` and consider a
  GitHub Release. Neither step belongs to this local versioning run.

Expected filenames from the current build scripts, **not existing beta.6 artifacts**:
`AstroPilot-1.0.0-beta.6-macos-arm64.zip` and
`AstroPilot-1.0.0b6-windows-x86_64-setup.exe`.

## Tester notes

Since beta.5, primary recommendations again require an actionable Mission and
continuous session window. Production ImagingField and AcquisitionIntent
support enables a choice of acquisition intent where applicable: single,
multiple, none, and legacy paths are handled in the UI. UserSelection carries
the chosen intent to Mission; a saved Mission can be reopened after reload
without a duplicate acceptance. Historical profiles are retained and require
explicit Bortle confirmation before recommendation. Editing a saved
configuration now has a contextual heading.

Weather provider reliability history is still immature: partial weather
validation and `CAUTION` are expected. This candidate does **not** claim
automatic intent progression, direct Session/Execution provenance, a mature
ProviderReliabilityReport, or advanced Learning.

The versioning and local checks alone do not certify installability. No beta.5
artifact/checksum is repurposed as a beta.6 build.
