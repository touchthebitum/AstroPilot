# Private Windows Sandbox launcher

These are the canonical reviewed templates for the private kits. They are not
an installer and are never executed by the application or by Python tests.

After verifying that the application candidate was built from the approved
full commit SHA, generate a new launcher in a **new** staging directory:

```text
python scripts/render_private_windows_launcher.py --source-sha FULL_APPROVED_SHA --output NEW_STAGING_DIRECTORY
```

Copy the resulting `Audit/controller.ps1`, `Audit/launch-sandbox.ps1`,
`sandbox-start.cmd`, `LANCER-TEST-WINDOWS.cmd` and `GERER-MES-DONNEES.cmd` into the new kit **before**
creating its manifest/ZIP. Do not reuse old launcher copies. Keep the existing
browser/application integrity checks, profile-source marker and result-export
restrictions in the private-kit assembler. The CMD bootstrap verifies the host
script hash before executing it. Its short encoded bootstrap does not embed
host paths or risk the Windows command-line length limit.

The host passes a Base64 **data argument** through the fixed Sandbox startup
command. Unicode, spaces, quotes and shell metacharacters in the host folder
never become executable text. The two existing Sandbox folder mappings stay
unchanged. No extra host file or mapping is added.

The Sandbox controller validates the schema, full source SHA, absolute paths
and host-kit/RESULTATS relationship before passing display-only JSON to the
application in `NIGHTMERIT_PRIVATE_COPY_CONTEXT`. The app validates it again
against its runtime build and actual guest data path. The app must never use
host paths to choose a profile, open a file, launch a command or import data.

If context is absent or malformed, the actual profile remains unchanged and
the app explicitly reports that host copy identification is unavailable.
Context is not included in the exported operator report. As before, the WSB
configuration contains the host paths needed for mapping and stays local.

`test_context.ps1` runs only the pure context functions under native Windows
PowerShell 5.1. It does not launch Sandbox, start the app, read a profile or
write a host folder. Native CI also tests the Python validator and API.

The second CMD entry point selects the separate offline data assistant through a
fixed mode argument, independent of display-only host context. Both bootstrap
scripts verify the same reviewed host script. Assistant downloads persist in
host `RESULTATS/SAUVEGARDES`. See [backup workflow](../../docs/profile-backup.md).
