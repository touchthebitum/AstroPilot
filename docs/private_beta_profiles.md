# Copies and data in the private beta

A kit identifies application sources, not the operator's saved records. Two
folders may contain the same application build and different profiles. The
ZIPs are distributed without operator data. Extracting a new ZIP does not
import a previous kit's profile.

## What the operator sees

**Version et données**, under **Options et aide** and in the footer, reads the
current runtime build, data-directory path and executable path. The empty
**Mes observations** view links directly to it and offers a return to the list.
This remains available before configuration and if configuration fails.

The display does not label a profile "empty", "personal" or "lost" based on a
folder name or a failed read. Identical kit names in Documents and another
folder are distinguished by their full data paths. The executable is shown in
a disclosure, so a development runtime is not presented as an installed kit.
Locations are fetched only on explicit opening, with no-store responses; their
text is never interpreted as HTML. `/v1/runtime-identity` stays non-sensitive.

## Where isolated private kits store records

| Platform | Data kept with the kit | How to resume |
| --- | --- | --- |
| Mac | `DONNEES-BETA/profil` | Use `DEMARRER-BETA.command` in that same extracted folder. |
| Windows Sandbox | Host kit's `RESULTATS/profil` | Close the old Sandbox normally, then run `LANCER-TEST-WINDOWS.cmd` in that same host folder. |

In Sandbox, `C:\NightMeritResults\profil` maps to the host kit's
`RESULTATS/profil`. Different host kits use that same guest path. The reviewed
private launcher now passes its host kit and RESULTATS locations as display-only
metadata, bound to the build and expected guest profile path. The panel shows
**Copie utilisée sur votre PC**, **Dossier de vos données sur votre PC**, and the
separately labeled internal Sandbox path. Two same-build kits in different host
folders therefore remain distinguishable.

If an older launcher supplies no context, or it fails validation, the panel
explicitly says that the host location could not be identified. It never derives
one from the guest path. Host metadata cannot choose the profile, trigger a file
read, or migrate data. See [private launcher templates](../scripts/private_beta_windows/README.md).

The ordinary installed application can use an OS data directory outside the
application. Always use the actual location reported by that runtime, not an
assumption about these private-kit paths.

## Resuming and updating

1. To continue the same test, reopen its existing folder and launcher. Do not
   extract the download again merely to resume yesterday's observation.
2. To test onboarding from scratch, extract the ZIP into a separate new folder.
   Its absence of old projects and observations is expected.
3. To update while retaining records, keep the old copy, stop its application
   normally, and prepare a separate destination copy. Verify saved records and
   their existing lineage/comparisons before using the new personal copy.
   If the destination already has data, stop: copying over it is not a merge.
4. Retain the old copy until the new one has been verified. Browser settings
   alone are not the saved profile; saved observations are read from the server.

The panel implements identification and guidance only. New kits can include a
separate offline [guided backup and restore assistant](profile-backup.md), opened
by their `GERER-MES-DONNEES` launcher after closing the observing application.
It verifies a backup and accepts explicit restoration only into an empty profile.
Older distributed kits remain unchanged; their first transfer still needs separate
preparation. No live import, automatic discovery, reset or merge is added here.

## Validation scope

API tests verify exact current locations, Unicode paths, no directory creation
or profile reads/writes, controlled errors, no-store and unchanged runtime
identity. Isolated browser tests cover Simple/Pro, narrow/wide layouts, explicit
fetch, failed and stale reads, text-only rendering, close/Escape and return to
observations. These are synthetic checks, not operator weather evidence.

## Version-independent beta data (opt-in for newly built kits)

Generate **new binaries** and launchers with `--data-mode stable` to enable the
shared private-beta store. Existing distributed kits remain isolated and are
never rewritten. The renderer default remains `isolated` for clean onboarding
and regression copies. Never attach a new stable launcher to an older binary:
preparation must support `--prepare-stable-beta FULL_BUILD_SHA` before any writer.

| Platform | Stable private-beta profile |
| --- | --- |
| Mac | `~/Library/Application Support/NightMerit/PrivateBeta/profil` |
| Windows host | Known Folder LocalApplicationData, then `NightMerit\PrivateBeta\profil` |
| Windows Sandbox | `C:\NightMeritData\profil`, through an additional explicit mapping |

This is separate from the normal installed AstroPilot profile. A stable launcher
holds a cross-version session lease until all its writers have stopped. A second
stable copy cannot acquire the lease. Per-kit results, browsers and diagnostics
remain separate; no Windows/browser security option is disabled. Windows context
v2 reports the real stable host data path but remains display-only. Legacy v1
and its isolated profile mapping remain supported.

Before the observing app **or** the offline assistant starts, the new binary
checks the storage protocol marker. It never searches previous kits. When a
registered profile moves to another application build, it creates and validates
a byte-preserving domain backup in `SAUVEGARDES-AUTO` beside the profile. Failure
blocks startup and leaves the profile and previous build marker unchanged. The
preparation itself never rewrites domain JSON. Same-build restarts do not create
repeated backups. Retained automatic backups are not pruned in this iteration.

The one-time adoption is separate: before first normal startup of a stable kit,
use the existing offline assistant to restore an explicitly selected verified
backup into its empty stable profile. Keep the previous copy. A nonempty,
unregistered folder is never silently adopted, reset or merged. If a normal
empty startup has already left traces, stop and prepare adoption separately;
this implementation does not silently remove traces to make a folder empty.
Subsequent stable-mode kits reuse the registered store automatically. Mac and
Windows are independent stores; this is not cross-device synchronization.

Private compiled stable-mode kits from source `917caae` have now been validated
on native Mac and Windows. Explicit assistant adoption before first normal
startup preserved projects, observations and comparisons; original copies were
retained. Windows was also reopened through the unmodified canonical launcher
in a fresh Sandbox. These are private validation results, not an official release.
Older isolated kits, including test30, retain their own profiles.

### Reproduce the compiled Windows upgrade-snapshot check

Use synthetic data only. Create a complete project/session/observation/comparison
fixture with the locked test environment:

```text
python scripts/ci/private_beta_windows/make_snapshot_fixture.py --output NEW_FIXTURE_DIRECTORY
```

In a separate Windows Sandbox, map the compiled candidate and fixture read-only,
and a new validation directory read-write. Invoke
`scripts/ci/private_beta_windows/frozen_stable_snapshot.ps1` with
`-CandidateDirectory`, `-FixtureDirectory`, `-WorkDirectory` (must not exist), and
`-BuildSha` (full target SHA). The check invokes the frozen binary's real
`--prepare-stable-beta` path while holding the parent session lease. It checks
that an upgrade creates exactly one automatic archive, leaves every domain byte
unchanged and advances the marker; same-build repetition must leave that archive
unchanged. Inspect the resulting archive with the production `inspect_backup`
reader and compare its returned documents with the fixture snapshot. Do not use
a mocked snapshot factory for this packaged check. Never map a personal store.

When diagnosing host folder mappings, verify the actual host location. Packaged
automation applications may virtualize AppData into their own cache: a directory
visible to such a process can still be absent from the path Windows Sandbox
shares. Do not substitute the automation application's cache for the operator's
stable store or change filesystem/browser security settings.
