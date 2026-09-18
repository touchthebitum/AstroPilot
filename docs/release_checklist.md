# Release checklist: 1.0.0-beta.3

Canonical version: `1.0.0b3`. Current status: technical validation recorded,
**distribution pending**. The native macOS clean-machine and Windows user-path
gates are open. The final tag and GitHub Release remain pending.

Source commit shared by the existing macOS and Windows candidate artifacts:
`c8566443c1caf612d122a8d217fe05884ac6aace`.
See [closed-beta artifact names, SHA-256 values, and validation history](closed_beta.md).

Checked items below reflect the confirmed validation record. Unchecked items
require a native test, retained evidence, or final documentation review; they
must be closed before distribution. This checklist does not execute builds or
publish a release.

## Mandatory gates

- [x] Same source commit for macOS and Windows, identified above.
- [ ] Confirm retained evidence of clean working trees during both final builds.
- [x] Canonical version `1.0.0b3`; tester label `1.0.0-beta.3`.
- [ ] Confirm full-suite macOS execution record is OK.
- [ ] Confirm full-suite Windows execution record is OK.
- [x] macOS build, Developer ID signature, accepted notarization, stapling,
  and Gatekeeper (`source=Notarized Developer ID`).
- [x] macOS final ZIP free of `._*` and `__MACOSX` entries.
- [x] Final macOS ZIP extracted and application revalidated by release pipeline.
- [ ] Real beta.3 macOS clean-machine test on the Mac mini — pending.
- [x] Windows PyInstaller build OK and Inno Setup installer compiled.
- [x] Per-user installation with no UAC elevation observed.
- [x] Windows launch validated.
- [ ] Retain explicit Start Menu launch evidence for the mandatory shortcut gate.
- [x] Windows data preservation and automatic profile rediscovery validated.
- [x] Windows update/reinstallation over existing install validated.
- [x] Windows uninstall validated.
- [x] Windows reinstall validated.
- [ ] Native Windows user paths with spaces/accented characters — pending.
- [x] Both candidate artifact SHA-256 values known (see below).
- [ ] Closed-beta documentation final review complete.
- [x] Candidate source/release commit identified above.
- [ ] Create final tag only after every validation gate is closed.
- [ ] Final GitHub Release — pending; no published release is recorded here.

Recent supplied validation: full suite 2641 passed, 0 failed, 1 skipped;
targeted version tests 161 passed; `uv lock --check` and `git diff --check`
passed. These are historical validation results, not tests run during this
documentation update. The aggregate suite result does not independently prove
both platform executions. Launch is confirmed; its Start Menu entry point is
not explicitly identified in the supplied native validation summary.

## Exact candidate identity

macOS: `AstroPilot-1.0.0-beta.3-macos-arm64.zip`

SHA-256: `75da488c31790d2dc5f8b521d57325375d6843a82b27db0e3901a3ec1d82f51f`

Windows: `AstroPilot-1.0.0b3-windows-x86_64-setup.exe`

SHA-256: `EC7AB793113FAACE22BB4691059FDB2BA002F2B4316C6465CDB8FC523B314DD8`

Windows size: 64,568,889 bytes.
Both use `c8566443c1caf612d122a8d217fe05884ac6aace`.

## Outside beta.3 scope

Windows Authenticode signing, MSI, auto-update, Linux, Android/iOS, Windows ARM,
new business features, and UI redesign. These are not missing beta.3 gates.
Historical beta.2 artifacts are superseded; the invalid AppleDouble-containing
ZIP must never be distributed (see the historical record in `closed_beta.md`).
