# Guided backup and restore for private kits

The separate **Retrouver mes données** assistant prepares a private ZIP and
restores it only into a new, empty profile. It does not merge copies, synchronize
Mac/Windows, discover other installations or alter existing comparisons/credits.
The ordinary **Version et données** panel remains read-only.

## Operator flow

1. Keep the old kit and close its application normally. Stop any Guardian or
   other tools writing that profile. Run `GERER-MES-DONNEES.command` (Mac) or
   `GERER-MES-DONNEES.cmd` (Windows) in the kit containing your records.
2. Choose **Télécharger ma sauvegarde**. Verify the ZIP exists in
   `DONNEES-BETA/SAUVEGARDES` on Mac or the host kit's `RESULTATS/SAUVEGARDES`
   on Windows. It contains personal data; keep it privately.
3. Close the assistant browser on Mac or close Windows Sandbox on Windows.
   Extract the new kit in a separate folder. On Windows place the backup ZIP
   in that new kit's host folder before launching the assistant; select it
   through the read-only `C:\NightMeritInput` mapping.
4. Run the new kit's data assistant, select the ZIP, inspect the project,
   session, observation and comparison counts, then explicitly confirm.
5. Close the assistant normally and run the usual launcher in that same new
   kit. Check **Mes projets**, **Mes observations** and an existing comparison.
   Retain the original copy until these checks pass.

Older kits lacking the assistant cannot export through it. The first migration
from those kits must still be prepared separately, with the original application
closed and the original copy retained. Adding a new command file to an old binary
is not an upgrade. This feature does not retroactively update distributed kits.

## Data and validation boundaries

- `--data-transfer` selects a separate loopback FastAPI process before the
  ordinary launcher starts. The server reserves port 8000 and never stops an
  existing process. Private launchers additionally retain their per-kit locks.
  It is not mounted in the live observing application and exposes no decision,
  session transition, credit or observation-creation endpoint.
- Backups preserve raw domain JSON bytes: user profile, legacy filter inventory,
  decision/selection/mission lineage, executions/evidence, forecast evidence,
  field observations and outcome comparisons. Counts identify stored execution
  aggregates as sessions. Files absent from the source are not synthesized.
- Logs, Guardian leases/scheduler authority, cursor signing keys and transient
  locks are not portable. The restored application regenerates its local cursor
  key normally. No runtime lease is resumed by restoring data.
- ZIP limits: 64 MiB compressed, 128 MiB domain data, 8 MiB per document,
  5,000 documents. Only explicit domain paths are accepted. Unknown domain
  files fail export rather than being silently lost; archive extras, duplicate
  names/JSON keys, special files, links, traversal and ambiguous paths fail.
- The manifest requires `nightmerit.profile_backup.v1` and the current canonical
  application version. Build hashes may differ. Future incompatible versions
  require explicit migration work. SHA-256 detects corruption, not authorship;
  use only backups from a trusted copy.
- Production deserializers and session/project credit read gates run on a
  disposable copy in a bounded subprocess, with no weather request. Validation
  never changes source bytes. Historical non-comparable comparisons remain
  non-comparable. Source documents are checked again after validation.
- A preview is read-only, single-use and expires after ten minutes. Another
  preview revokes the previous confirmation. Confirmation revalidates and
  rechecks that the destination is empty, including hidden files. Files are
  staged beside the destination, synchronized where supported, then published
  by directory rename. A failed publication restores the prior empty directory;
  an ambiguous post-publication I/O failure instructs the operator to inspect
  the destination rather than retry an overwrite.
- This is an offline workflow. Port/kit locks do not exclude arbitrary external
  writers; the application and Guardian must be stopped. No attempt is made
  to take a transactional live snapshot across stores or reconcile concurrent
  edits. Network shares and symlink/junction data directories are unsupported.
- The assistant uses a random per-process token, same-origin POST checks,
  loopback Host allow-list, no-store and a restrictive CSP. ZIP filenames and
  preview values are never interpreted as HTML or executable commands.

## Packaging and checks

Render launchers from the approved full source commit into a new staging folder:

```text
python scripts/render_private_macos_launcher.py --source-sha FULL_SHA --output NEW_FOLDER
python scripts/render_private_windows_launcher.py --source-sha FULL_SHA --output NEW_FOLDER
```

Build the Mac helper from the rendered `launcher.py`; include its three command
files in the new kit before generating the integrity manifest. The Windows
renderer produces both CMD entry points plus the reviewed Audit sources. Both
must accompany the matching newly built application. Dedicated assistant browser
preferences direct downloads to a persistent private folder; no personal browser
profile is used. Windows mappings and host display metadata are unchanged.

Synthetic tests cover byte preservation, production reads, invalid credits,
corrupt/malicious archives, destination refusal, publication failure, token and
confirmation checks, UI preview/failure/replay and launcher dispatch/isolation.
Native Windows/macOS CI runs the transfer tests. This does not replace manual
packaged-kit verification, nor does it constitute an imaging or weather test.
