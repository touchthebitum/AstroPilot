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

## Where the current private kits store records

| Platform | Data kept with the kit | How to resume |
| --- | --- | --- |
| Mac | `DONNEES-BETA/profil` | Use `DEMARRER-BETA.command` in that same extracted folder. |
| Windows Sandbox | Host kit's `RESULTATS/profil` | Close the old Sandbox normally, then run `LANCER-TEST-WINDOWS.cmd` in that same host folder. |

In Sandbox, `C:\NightMeritResults\profil` maps to the host kit's
`RESULTATS/profil`. Different host kits use that same guest path. To distinguish
copies, also check the host folder used to launch the kit and the reported
build. The UI cannot resolve a host path that was never passed into Sandbox;
it does not invent one.

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

This change implements identification and guidance only. It adds no profile
import, merge, automatic discovery of other copies, reset, folder opener or
background migration. No launcher, sandbox mapping or filesystem permission is
changed. A future transfer flow needs its own conflict handling and validation.

## Validation scope

API tests verify exact current locations, Unicode paths, no directory creation
or profile reads/writes, controlled errors, no-store and unchanged runtime
identity. Isolated browser tests cover Simple/Pro, narrow/wide layouts, explicit
fetch, failed and stale reads, text-only rendering, close/Escape and return to
observations. These are synthetic checks, not operator weather evidence.
