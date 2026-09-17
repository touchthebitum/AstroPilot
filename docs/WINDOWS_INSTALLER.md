# Win-4: Windows per-user installer

Win-4 wraps the existing PyInstaller onedir build with Inno Setup. It does
not rebuild the application, change product versioning, or introduce signing.

## Prerequisites and build order

- Windows 11 x86_64 and a prepared project environment (Python 3.11–3.13).
- An existing complete `dist/AstroPilot` build, including `AstroPilot.exe`
  and its `_internal` tree. Keep the whole directory together.
- Inno Setup 7 installed manually, including its preprocessor and `ISCC.exe`.
  Inno Setup 6.3+ remains supported as a fallback.
  The build tool never downloads or installs it.

Run from the repository root in PowerShell:

```powershell
# Step 1: application build, only when a new application build is needed.
uv run --locked --no-sync python scripts/build_windows.py

# Step 2: installer build, consumes the existing application build unchanged.
uv run --locked --no-sync python scripts/build_windows_installer.py
```

Step 1 retains its existing cleanup behavior for `build` and `dist`; Step 2
never cleans either directory and never calls Step 1.

If automatic compiler discovery fails:

```powershell
uv run --locked --no-sync python scripts/build_windows_installer.py --iscc "C:\Program Files\Inno Setup 7\ISCC.exe"
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

The only version source is `project.version` in `pyproject.toml`. The tool
passes it unchanged as `/DAppVersion` for `AppVersion` and the output filename.
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
  files in the new payload replace installed files. No broad cleanup is added;
  files absent from a newer payload may remain until uninstall.
- `CloseApplications=yes` and `RestartApplications=yes` use Inno Setup's normal
  Restart Manager behavior, with no forced termination. Automatic restart
  depends on application registration with Windows `RegisterApplicationRestart`;
  these directives alone do not guarantee that AstroPilot will relaunch. Check
  actual open-application behavior natively; this increment does not change
  the launcher.
- Uninstall removes installed program files and owned shortcuts using Inno's
  normal uninstall log. There are no custom delete rules.
- The installer never creates, manages, copies, or deletes the application data
  directory. Profiles, projects, and logs must survive install, update, uninstall,
  and reinstall. Reinstall lets the existing application find its previous data.

The setup is currently unsigned. Authenticode signing, certificates, MSI,
onefile builds, macOS packaging, and business logic changes are outside Win-4.

## Automatic contract validation

```powershell
uv run --locked --no-sync python -m pytest -q tests/architecture/test_windows_installer_contract.py
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
