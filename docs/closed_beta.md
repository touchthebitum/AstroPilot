# Closed beta: 1.0.0-beta.3

Canonical version: `1.0.0b3`. Tester label: `1.0.0-beta.3`.
The current multi-platform candidate replaces beta.2. Technical packaging
validation is recorded below; distribution approval is still pending.
No final tag or GitHub Release is recorded as created/published, and no download
URL is available in this record.

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

### Windows

- PyInstaller application build and compiled Inno Setup per-user installer.
- Real installation under `{userpf}\AstroPilot`; no UAC elevation observed.
- Launch validated.
- Update/reinstallation over the existing installation, uninstall, and reinstall
  validated.
- User data under `%LOCALAPPDATA%\AstroPilot` preserved; existing profile
  automatically found after reinstall.
- Stable AppId: `A3B620CB-8E79-4B91-8DAB-4CF1BEE63985`.

See [Windows installer contract and reusable native procedure](WINDOWS_INSTALLER.md).

### Recent validation record

Reported after the beta.3 version bump (not rerun by this documentation update):

- Full suite: 2641 passed, 0 failed, 1 skipped.
- Targeted version tests: 161 passed.
- `uv lock --check`: passed.
- `git diff --check`: passed.

The supplied aggregate suite result is not a separate per-platform execution
record. The release checklist requires macOS and Windows suite evidence before
final approval; do not infer a missing platform record from this aggregate.

## Pending before distribution

- Real beta.3 macOS clean-machine user test on the Mac mini.
- Native Windows test with spaces/accented characters in the user path.
- Final review of all [release gates](release_checklist.md), including clean
  working trees at final build time and platform-specific full-suite records.
- Closed-beta documentation review, then final tag/GitHub Release only after
  complete validation. Neither is recorded as created/published.

The macOS pipeline's extracted-ZIP checks do not close the clean-machine gate.
Automated Windows path checks do not close the native user-path gate.

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
