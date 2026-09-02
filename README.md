# AstroPilot

AI-powered astrophotography planning platform.

Current targets:
- macOS
- Android
- iOS

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

## User data

AstroPilot requires an existing directory containing a valid
`user_profile.json`. Automatic onboarding and profile creation are not yet
provided. Point AstroPilot to that directory before launching it:

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
uv run --locked --no-sync python -m uvicorn astropilot.app:app \
  --host 127.0.0.1 \
  --port 8000
```

Open <http://127.0.0.1:8000/> in a browser.
