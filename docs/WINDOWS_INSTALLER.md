# Win-4: Windows per-user installer

Win-4 wraps a verified PyInstaller onedir build with Inno Setup. The release
procedure rebuilds the application from the release checkout before packaging.

## Recorded beta.3 status

This is a historical beta.3 validation record (the current local versioning
candidate is beta.7; see [release checklist](release_checklist.md)). Beta.3 was
`1.0.0-beta.3` (canonical `1.0.0b3`),
from source commit `c8566443c1caf612d122a8d217fe05884ac6aace`.

- Artifact: `AstroPilot-1.0.0b3-windows-x86_64-setup.exe`
- SHA-256: `EC7AB793113FAACE22BB4691059FDB2BA002F2B4316C6465CDB8FC523B314DD8`
- Size: 64,568,889 bytes.
- Validated natively: installation under `{userpf}\AstroPilot` without observed
  UAC elevation, launch, update/reinstallation over the existing installation,
  uninstall, reinstall, and preservation/automatic rediscovery of the user
  profile under `%LOCALAPPDATA%\AstroPilot`.
- Native user-path test: **PASS**, standard account `Franck Testé`,
  `USERPROFILE=C:\Users\Franck Testé` (space and accented character).
  Installation without observed UAC elevation, normal launch and Start Menu
  launch, fresh onboarding, and profile creation validated. Closing/reopening
  returned to "Préparer ma nuit" with data preserved.
- Full suite Windows beta.3: 2641 passed, 0 failed, 1 skipped (recorded result;
  not rerun during this documentation update).
- Authenticode was outside beta.3 scope. At the time of this record, tag and
  GitHub Release were listed as pending; this is not beta.7 status.

The checklist below is a reusable procedure, not an assertion that every
individual observation (for example optional shortcuts or automatic restart)
was recorded for beta.3. The validated summary above is historical.

## Prerequisites and build order

- Windows 11 x86_64, Python 3.11–3.13, and `uv` available on PATH.
- A clean, committed release-candidate checkout and a current `uv.lock`.
- Inno Setup 7 installed manually, including its preprocessor and `ISCC.exe`.
  Inno Setup 6.3+ remains supported as a fallback.
  The build tool never downloads or installs it.

Run from the repository root in PowerShell:

```powershell
# Step 1: mandatory application rebuild. The script synchronizes the packaging
# environment against the lock, clears old build output, and injects HEAD SHA.
python scripts/build_windows.py

# Step 2: verify executable runtime version and build SHA, then compile setup.
python scripts/build_windows_installer.py
```

Both steps require a clean committed checkout. Step 1 clears `build` and `dist`;
Step 2 never cleans either directory. Run both steps for every release candidate.
Step 2 executes `AstroPilot.exe --runtime-identity` without starting the UI and
requires its version, seven-character build SHA, and x86_64 architecture to
match the project and current checkout. Missing or invalid identity stops before
Inno Setup runs.

If automatic compiler discovery fails:

```powershell
python scripts/build_windows_installer.py --iscc "C:\Program Files\Inno Setup 7\ISCC.exe"
```

Alternatively set `$env:ISCC_PATH` to the full `ISCC.exe` path. CLI takes
precedence over the environment; an invalid configured path fails explicitly.
Discovery otherwise tries PATH, then standard locations under
`$env:ProgramFiles(x86)`, `$env:ProgramFiles`, and `$env:LOCALAPPDATA\Programs`.
All standard locations are checked for `Inno Setup 7\ISCC.exe` first, then
for `Inno Setup 6\ISCC.exe`. If no compiler is found, the tool fails explicitly.

Output: `dist/installer/AstroPilot-<version>-windows-x86_64-setup.exe`.
The build tool prints its absolute path after successful compilation.

## Version and installation contract

The expected version comes from `project.version` in `pyproject.toml`. Only
after executable identity validation does the tool pass it unchanged as
`/DAppVersion` for `AppVersion` and the output filename.
No numeric conversion or `VersionInfoVersion` override is introduced.

Immutable product AppId: `A3B620CB-8E79-4B91-8DAB-4CF1BEE63985`.
Never change this GUID after the first distributed installation: it identifies
the previous installation and its uninstall log for subsequent updates.

- Program: `{userpf}\AstroPilot`, normally
  `%LOCALAPPDATA%\Programs\AstroPilot`. The directory selection page is disabled.
- Application data: `%LOCALAPPDATA%\AstroPilot`, strictly separate from program
  files. Existing application data-path overrides remain unchanged.
- Per-user installation with `PrivilegesRequired=lowest`; no UAC elevation or
  administrative-mode override.
- The entire onedir tree is copied recursively under `{app}`.
- User Start Menu shortcut is mandatory; user Desktop shortcut is optional
  via the unchecked `desktopicon` task. Both launch `{app}\AstroPilot.exe`.
- Updates use the same AppId and previous installation directory; program
  files in the new payload replace installed files. Before copying, `[InstallDelete]`
  removes only `{app}\_internal\astropilot-*.dist-info` (matching directories
  and their contents). This retires AstroPilot metadata left by older payloads
  that could otherwise make `importlib.metadata.version("astropilot")` report an
  obsolete version. Any metadata supplied by the new payload is then copied
  normally. Other packages, program files, and user files are not cleanup targets;
  other files absent from a newer payload may remain until uninstall.
- `CloseApplications=yes` and `RestartApplications=yes` use Inno Setup's normal
  Restart Manager behavior, with no forced termination. Automatic restart
  depends on application registration with Windows `RegisterApplicationRestart`;
  these directives alone do not guarantee that AstroPilot will relaunch. Check
  actual open-application behavior natively; this increment does not change
  the launcher.
- Uninstall removes installed program files and owned shortcuts using Inno's
  normal uninstall log. There are no custom uninstall delete rules.
- The installer never creates, manages, copies, or deletes the application data
  directory. Profiles, projects, and logs must survive install, update, uninstall,
  and reinstall. Reinstall lets the existing application find its previous data.

The setup is currently unsigned. Authenticode signing, certificates, MSI,
onefile builds, macOS packaging, and business logic changes are outside Win-4.

## Beta.4 upgrade metadata regression

Native beta.4 validation from source `423bb6a` showed a clean-build runtime
version of `1.0.0b4`, but an upgrade over an older installation reported
`1.0.0b2` with the same new build identity. The old
`{app}\_internal\astropilot-1.0.0b2.dist-info` directory had survived the copy.
The narrow cleanup above addresses this installed-program residue without
changing version lookup, AppId, per-user installation, or user-data handling.
The recorded beta.3 status above is historical and unchanged.

Inno processes [InstallDelete](https://jrsoftware.org/ishelp/topic_installdeletesection.htm)
before [Files](https://jrsoftware.org/ishelp/topic_installorder.htm).
The `filesandordirs` type removes matching metadata directories recursively;
the wildcard is confined to the AstroPilot metadata name under `{app}\_internal`.
No whole-program or user-data cleanup is introduced. This also applies on fresh
install/reinstall and is harmless when no matching metadata exists. An interrupted
installation may require rerunning setup to restore the current payload metadata;
this change does not promise transactional rollback of deleted obsolete metadata.

Contract tests simulate cleanup followed by payload copy, with real Python
metadata discovery for directory and archive layouts. They do not compile or
execute Inno Setup. Native retest remains required: upgrade the old installation,
confirm no beta.2 metadata survives, verify `/v1/runtime-identity` reports `1.0.0b4`
and the new build, then validate launch, data preservation, uninstall, and reinstall.

## Automatic contract validation

```powershell
uv run --locked --extra test python -m pytest -q tests/architecture/test_windows_installer_contract.py
```

These tests use a stub compiler runner and require no Inno Setup installation.
They do not replace native installation validation.

## Native Windows 11 validation checklist

Record the application version and runtime build commit. Before installation,
back up existing data and record profile/project/log contents for comparison.

### A. Standard account installation

- [ ] Compile the real setup only after automatic tests and static review pass.
- [ ] Run as a standard user: no UAC request.
- [ ] Confirm complete program tree under the user's Program Files directory.
- [ ] Launch through the user Start Menu shortcut.
- [ ] Verify runtime version and build commit against the existing onedir build.
- [ ] Verify optional Desktop shortcut only when its task is selected.

### B. Preexisting data

- [ ] Existing profile intact and usable.
- [ ] Existing projects intact and usable.
- [ ] Existing logs intact.

### C. Update

- [ ] Build a subsequent installer retaining exactly the same AppId.
- [ ] Previous installation recognized; same program directory and uninstall entry.
- [ ] Updated payload replaces corresponding program files.
- [ ] Obsolete AstroPilot metadata under `{app}\_internal` removed before copy;
  other package metadata and user data preserved.
- [ ] Installed `/v1/runtime-identity` matches the clean build version and commit.
- [ ] Profile, projects, and logs preserved.
- [ ] Test with AstroPilot open: observe normal close prompt and file replacement.
- [ ] Observe actual restart behavior; if no automatic restart, verify manual launch.

### D. Uninstall

- [ ] Installed program files removed.
- [ ] Owned Start Menu and Desktop shortcuts removed.
- [ ] `%LOCALAPPDATA%\AstroPilot` and all its contents retained.

### E. Reinstall

- [ ] Reinstall setup; previous application data automatically found and usable.

### F. User paths

- [ ] Repeat with spaces in the Windows user path.
- [ ] Repeat with accented characters in the Windows user path.

## Inno Setup references

- [PrivilegesRequired](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
- [AppId](https://jrsoftware.org/ishelp/topic_setup_appid.htm)
- [CloseApplications](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm)
- [RestartApplications](https://jrsoftware.org/ishelp/topic_setup_restartapplications.htm)
- [VersionInfoVersion](https://jrsoftware.org/ishelp/topic_setup_versioninfoversion.htm)
