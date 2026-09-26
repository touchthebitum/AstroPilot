# Changelog

## 1.0.0-beta.7 — local release preparation (not built or published)

- Added editable progress per acquisition intent and remaining-work projection;
  completed intents and completed legacy projects no longer become candidates.
- Added durable execution sessions, audited per-session progress credits, and
  restoration of execution history and mission progress after reload.
- Made recommendation refusals explainable through structured intent
  eligibility, actionability, and productivity breakdowns.
- Corrected hourly cloud sampling across quarter-hour forecast slices and
  clarified weather reliability wording while retaining intentional caution.
- Corrected fixed-window rollover after midnight and made the core time
  pipeline, season sampling, and presentation safe across DST transitions.
- Changed the user-facing product name to NightMerit while retaining the
  AstroPilot technical/distribution identity for upgrade compatibility.
- Clarified acquisition-intent and hardware-filter wording; legacy filter
  inventories are non-authoritative rather than silently constraining choices.
- Preserved historical decision compatibility with current schema v9 and
  legacy schemas v1-v8.
- Kept Windows packaging unsigned; native Windows build, install, upgrade, and
  uninstall validation remain release gates.

See [the complete beta.7 notes](release_notes_beta7.md) and
[release checklist](release_checklist.md).

## 1.0.0-beta.6 — historical versioning baseline

- Restored primary recommendation actionability: an actionable recommendation
  requires a real, usable Mission and a continuous actionable session window.
- Brought ImagingField and AcquisitionIntent into the production recommendation
  path, with intent choices in the UI for a single choice, multiple choices,
  no eligible choice, and legacy recommendations.
- Propagated the user's selected acquisition intent into the Mission and
  restored the saved Mission after reload without accepting it again.
- Preserved historical profiles through explicit Bortle confirmation, without
  resetting existing setups, sessions, projects, or other preferences.
- Corrected the configuration assistant's editing label for an already saved
  configuration.
- Weather provider reliability history is not yet mature: partial weather
  validation and `CAUTION` remain intentional, not a guarantee of forecast
  reliability.

Not included: automatic progression by intent, direct Session/Execution
provenance, a mature ProviderReliabilityReport, or advanced Learning.

## Historical notes

v0.1

- Ajout scoring météo
- Ajout scoring lune
- Ajout top objets
