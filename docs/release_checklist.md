# Release checklist: 1.0.0-beta.3

Canonical version: `1.0.0b3`.
All beta.3 validation gates are closed. Tag creation and GitHub Release remain pending.

Source commit shared by the existing macOS and Windows candidate artifacts:
`c8566443c1caf612d122a8d217fe05884ac6aace`.
See [closed-beta artifact names, SHA-256 values, and validation history](closed_beta.md).

Checked items below reflect the confirmed validation record. Unchecked items
are the remaining tag creation and GitHub Release steps. This checklist does not execute builds or
publish a release.

## Mandatory gates

- [x] Same source commit for macOS and Windows, identified above.
- [x] Confirm retained evidence of clean working trees during both final builds.
- [x] Canonical version `1.0.0b3`; tester label `1.0.0-beta.3`.
- [x] Full suite macOS beta.3: 2642 passed, 0 failed, 44 warnings; 25.67 s.
- [x] Full suite Windows beta.3: 2641 passed, 0 failed, 1 skipped.
- [x] macOS build, Developer ID signature, accepted notarization, stapling,
  and Gatekeeper (`source=Notarized Developer ID`).
- [x] macOS final ZIP free of `._*` and `__MACOSX` entries.
- [x] Final macOS ZIP extracted and application revalidated by release pipeline.
- [x] Real beta.3 macOS clean-machine test on the Mac mini — PASS.
- [x] Windows PyInstaller build OK and Inno Setup installer compiled.
- [x] Per-user installation with no UAC elevation observed.
- [x] Windows launch validated.
- [x] Native Windows Start Menu launch validated.
- [x] Windows data preservation and automatic profile rediscovery validated.
- [x] Windows update/reinstallation over existing install validated.
- [x] Windows uninstall validated.
- [x] Windows reinstall validated.
- [x] Native Windows user path `C:\Users\Franck Testé` (space/accent) — PASS.
- [x] Both candidate artifact SHA-256 values known (see below).
- [x] Final release review, including closed-beta documentation review, complete.
- [x] Candidate source/release commit identified above.
- [ ] Create final tag only after every validation gate is closed.
- [ ] Final GitHub Release — pending; no published release is recorded here.

Native evidence is recorded in [closed-beta status](closed_beta.md): the macOS
candidate SHA-256 was verified before extraction on a clean Mac mini test
account, followed by double-click launch without a macOS alert, fresh onboarding,
profile creation, and preserved data after reopening. The Windows test used
standard account `Franck Testé`, with no observed UAC elevation, normal/Start Menu
launch, fresh onboarding, profile creation, and preserved data after reopening.
Both returned to "Préparer ma nuit".

The platform full-suite results above are supplied validation records, not tests
rerun during this documentation update. Earlier targeted version tests: 161
passed; `uv lock --check` and `git diff --check` passed.
Retained evidence confirms that both final artifacts were built from source
commit `c8566443c1caf612d122a8d217fe05884ac6aace`. Before the final Windows build
and the signed/notarized macOS release build, each working tree was clean,
`main == origin/main`, and HEAD matched that source commit. Final docs/release
review is complete before tag creation and GitHub Release; neither publication
step has been performed.

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
