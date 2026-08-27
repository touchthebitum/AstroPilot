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

The `set` and `clear` commands update `data/user_profile.json`. Treat that file as local user data and review it separately before committing changes.
