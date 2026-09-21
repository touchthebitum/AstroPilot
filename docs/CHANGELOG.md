# Changelog

## 1.0.0-beta.6 — local versioning candidate (not built or published)

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
