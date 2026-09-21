# AstroPilot

AI-powered astrophotography planning platform.

Local release candidate: **1.0.0-beta.6** (canonical version `1.0.0b6`).
Versioning is under local review: no beta.6 build, tag, or GitHub Release has
been created. After the versioning commit, macOS and Windows must both be built
from that same commit. The future tag is `v1.0.0-beta.6`.

The historical `v1.0.0-beta.5` tag already exists. See the
[beta.6 candidate notes and remaining gates](docs/release_checklist.md).

Published historical baseline: **v1.0.0-beta.4** (canonical version `1.0.0b4`).

Published historical baseline: **v1.0.0-beta.3** (canonical version `1.0.0b3`).
Current beta targets: macOS Apple Silicon and Windows x86_64. Linux, Android,
iOS, and Windows ARM are outside this beta.

Historical beta.3 validation record (recorded before publication):

Both beta.3 artifacts use source commit
`c8566443c1caf612d122a8d217fe05884ac6aace`. macOS signing, notarization,
stapling, Gatekeeper, and ZIP extraction checks are validated. Windows native
installation, launch, update, uninstall, reinstall, and data preservation are
validated. The beta.3 clean-machine test on the Mac mini, native Windows user
path with spaces/accented characters, and Windows Start Menu launch have passed.
Full suites were validated on macOS and Windows for beta.3. This is a historical
validation record, not a validation of beta.6.

See [closed-beta status and artifact SHA-256 values](docs/closed_beta.md),
[release gates](docs/release_checklist.md), and
[Windows installer documentation](docs/WINDOWS_INSTALLER.md).

Features:
- Sky quality analysis
- Object recommendation engine
- Weather integration
- Moon impact analysis
- SQM prediction
- GPS-based location detection
- Astrophotography session planning

## Prerequisites

- Python 3.11, 3.12, or 3.13 (`>=3.11,<3.14`)
- [uv](https://docs.astral.sh/uv/)

## Environment setup

Synchronize the locked runtime environment:

```bash
uv sync --locked
```

For development and tests, include the `test` extra:

```bash
uv sync --locked --extra test
```

Commands below use `--no-sync` and therefore assume that the corresponding
synchronization step has already completed.

## User data (source checkout and installed wheel)

For the web UI, point AstroPilot to a writable user-data directory. It can
create `user_profile.json` during initial configuration; command-line decision
usage still requires a valid profile. Set the directory before launching it:

```bash
export ASTROPILOT_DATA_DIR=/path/to/astropilot-data
```

The configured directory must already exist. A repository checkout includes
the current local profile at `data/user_profile.json`, which is used when
`ASTROPILOT_DATA_DIR` is not set. An installed wheel does not include that
local profile.

## Tests

Run tests through the synchronized project interpreter:

```bash
uv run --locked --no-sync python -m pytest -q
```

Using `python -m pytest` avoids accidentally invoking a global `pytest` tied
to a different Python environment.

## Command-line usage

Run AstroPilot from the project directory with the locked environment:

```bash
uv run --locked --no-sync astropilot --mode tonight
```

Available display modes are `tonight`, `portfolio`, `calendar`, and `full`:

```bash
uv run --locked --no-sync astropilot --mode portfolio
uv run --locked --no-sync astropilot --mode calendar
uv run --locked --no-sync astropilot --mode full
```

Compare equipment for an object or force a complete target analysis:

```bash
uv run --locked --no-sync astropilot --object M31
uv run --locked --no-sync astropilot --target-object IC1396
```

Inspect, configure, or clear a project's per-filter hour targets:

```bash
uv run --locked --no-sync astropilot --filter-targets-show IC1396
uv run --locked --no-sync astropilot --filter-targets-set IC1396 Ha=6 OIII=5 SII=4
uv run --locked --no-sync astropilot --filter-targets-clear IC1396
```

The `set` and `clear` commands update `user_profile.json` in
`ASTROPILOT_DATA_DIR` when configured, or `data/user_profile.json` in a
repository checkout otherwise. Treat that file as local user data and review
it separately before committing changes.

## API and UI

Start the API and bundled UI after synchronizing the runtime environment:

```bash
uv run --locked --no-sync astropilot-app
```

AstroPilot starts locally at <http://127.0.0.1:8000/> and opens that address
in the default browser. A second launch detects the existing AstroPilot
instance and reopens it. If another application is using port 8000,
AstroPilot stops without changing ports or terminating that application.

Launcher diagnostics are stored in `~/Library/Logs/AstroPilot/AstroPilot.log`.
Provide this log when reporting a startup problem.

## Local macOS application build

Create the isolated packaging environment and build the Apple Silicon app:

```bash
UV_PROJECT_ENVIRONMENT=.venv-packaging uv sync --locked --extra packaging
.venv-packaging/bin/python scripts/build_macos.py
```

The application bundle is written to `dist/AstroPilot.app`.

For a Developer ID release build, first store notarization credentials in the
login keychain with Apple's interactive tool (never put credentials in this
repository):

```bash
xcrun notarytool store-credentials "astropilot-notary"
```

Then run the release workflow with an existing Developer ID Application
identity and that keychain profile:

```bash
ASTROPILOT_CODESIGN_IDENTITY="Developer ID Application: Name (TEAMID)" \
  .venv-packaging/bin/python scripts/release_macos.py \
  --notary-profile "astropilot-notary"
```

The workflow verifies the signature, notarizes and staples the app, checks it
with Gatekeeper, and writes the versioned ZIP and SHA-256 sidecar under `dist/`.

The final release ZIP excludes AppleDouble (`._*`) and `__MACOSX` entries.
The workflow extracts that ZIP and rechecks the extracted application signature,
stapling, and Gatekeeper before generating its SHA-256 sidecar. These pipeline
checks are complemented by the passed native beta.3 clean-machine test.
