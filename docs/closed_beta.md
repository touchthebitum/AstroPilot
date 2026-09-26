# Historical closed beta record: 1.0.0-beta.3

Canonical version: `1.0.0b3`. Tester label: `1.0.0-beta.3`.
This document preserves the beta.3 artifact and validation record; the current
local versioning candidate is beta.7 (see [release checklist](release_checklist.md)).
Beta.3 replaced beta.2. The historical text below describes what was recorded
at that time, not the present publication status.

## Candidate artifacts

Both artifacts use the same source commit:
`c8566443c1caf612d122a8d217fe05884ac6aace`.
This identifies their build sources; a later documentation commit does not
change the sources or identity of these existing artifacts.

| Platform | Artifact | SHA-256 |
| --- | --- | --- |
| macOS arm64 | `AstroPilot-1.0.0-beta.3-macos-arm64.zip` | `75da488c31790d2dc5f8b521d57325375d6843a82b27db0e3901a3ec1d82f51f` |
| Windows x86_64 | `AstroPilot-1.0.0b3-windows-x86_64-setup.exe` | `EC7AB793113FAACE22BB4691059FDB2BA002F2B4316C6465CDB8FC523B314DD8` |

Windows installer size: 64,568,889 bytes.

## Validated

### macOS

- Build and Developer ID signature: Franck Perruchoud (`C6BY4FF54H`).
- Apple notarization accepted; stapling validated.
- Gatekeeper: `source=Notarized Developer ID`.
- Final ZIP protected against AppleDouble (`._*`) and `__MACOSX` entries.
- Final ZIP extracted and its application revalidated by the release pipeline
  (signature, stapling, Gatekeeper).
- Native beta.3 clean-machine test: **PASS**, on a clean test account on the
  Mac mini. The candidate ZIP listed above had its SHA-256 verified before
  extraction. Double-click launch produced no macOS alert; browser and UI
  opened normally. The old data directory was removed, fresh onboarding was
  confirmed, and a profile was created. After closing/reopening, the app
  returned to "Préparer ma nuit" with data preserved.

### Windows

- PyInstaller application build and compiled Inno Setup per-user installer.
- Real installation under `{userpf}\AstroPilot`; no UAC elevation observed.
- Launch, including from the Windows Start Menu, validated.
- Native complex user-path test: **PASS**, using standard account `Franck Testé`
  with `USERPROFILE` set to `C:\Users\Franck Testé` (space and accented character).
  No UAC elevation observed during installation; normal launch, fresh onboarding,
  and profile creation confirmed. After closing/reopening, the app returned to
  "Préparer ma nuit" with data preserved.
- Update/reinstallation over the existing installation, uninstall, and reinstall
  validated.
- User data under `%LOCALAPPDATA%\AstroPilot` preserved; existing profile
  automatically found after reinstall.
- Stable AppId: `A3B620CB-8E79-4B91-8DAB-4CF1BEE63985`.

See [Windows installer contract and reusable native procedure](WINDOWS_INSTALLER.md).

### Recent validation record

Reported after the beta.3 version bump (not rerun by this documentation update):

- Full suite macOS beta.3: 2642 passed, 0 failed, 44 warnings; 25.67 s.
- Full suite Windows beta.3 (already recorded): 2641 passed, 0 failed, 1 skipped.
- Targeted version tests: 161 passed.
- `uv lock --check`: passed.
- `git diff --check`: passed.

## Final review complete; publication pending

Retained evidence confirms clean working trees, `main == origin/main`, and HEAD
at `c8566443c1caf612d122a8d217fe05884ac6aace` before both final builds (Windows
installer and signed/notarized macOS release). Final docs/release review is
complete; the beta.3 validation gates were closed in the historical record.

At the time of this beta.3 record, tag creation and GitHub Release were still
listed as pending. This is not a statement about the current beta.7 candidate.

## Outside beta.3 scope

Authenticode Windows signing, MSI, auto-update, Linux, Android/iOS, Windows ARM,
new business features, and UI redesign.

## Historical beta.2 artifacts — superseded

- Invalid beta.2 ZIP SHA-256:
  `1bdeea2c233fae8eabee5724a3a6478b2574edbc05d915a74cb582ab353a3f52`.
  Contains AppleDouble entries. **Must never be distributed.**
- Technically corrected beta.2 ZIP SHA-256:
  `5f899f0b28a10728fe3733daf72ec243b912883762d98be3002c29ea4e0ef09c`.
  Historical only; superseded by beta.3 as the multi-platform candidate.

Recent increments: PR #222 (Windows runtime/packaging validation), PR #223
(per-user Windows installer), PR #224 (version bump to `1.0.0b3`).
