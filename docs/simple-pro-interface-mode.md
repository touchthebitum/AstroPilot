# Simple / Pro — first presentation batch

Baseline: cf0bd4cf91de0597072840aa734bee03f2501465 (PR #307).

`nightmerit.ui-mode.v1` is an origin-local UI preference. Only `simple` and
`pro` are accepted; missing, invalid, or unreadable storage defaults to Simple.
Storage failures keep the current in-memory presentation usable. Storage events
(including storage clear) synchronize tabs. No backend schema or scientific
handler reads this preference.

The native labelled select exposes the selected mode and keyboard focus.
`data-ui-mode` controls technical visibility. Shared details panels are closed
in Simple and open in Pro; users can still explicitly open them in Simple.
Switching modes never clears fields, changes filter values, requests data,
recalculates a decision, or changes recovery state. Advanced active filters
remain active when their panel closes.

Tonight actions: Mes observations / Mon historique / Ajouter une observation.
Pro restores the longer existing action labels. Weather source and retrieval
are Pro-only; freshness and coverage remain visible for informed decisions.
Observation keeps quick entry, scientific measurements, and all recovery guards.
Outcome comparisons retain comparability and blocking reasons; traceability is
in Détails techniques. History keeps Ce site outside advanced filters, with
statistics and provenance in disclosures; exact coordinates, mode and coverage
columns are Pro-only. Technical IDs remain available in history detail.

Next batch: broader wording audit,
recovery diagnostic wording. This batch
intentionally retains scientific terminology inside explicitly opened details.

## Validation

- Complete suite with the bundled Node executable on PATH and local loopback
  access: 4795 passed (44 existing warnings).
- Final targeted UI/API suite including simplified UX: 116 passed.
- Bundled Node syntax check and `git diff --check`: passed.
- `tests/ui/simple_pro_browser.cjs`: Chrome/Playwright with mocked API routes;
  real DOM checks in Simple and Pro at 390px and 1280px, populated history,
  long traceability, local preference reload, invalid value, multi-tab storage,
  HFR/RMS and selection retention, decision/mission/recovery identity and
  no additional request on toggle. This is a presentation smoke test; API
  semantics are covered separately by the Python suite.

Example browser command (use available Node and Playwright installation):
`NODE_PATH=/path/to/node_modules node tests/ui/simple_pro_browser.cjs`

Simple shows a clickable advanced-filter summary, derived from the live form:
`Filtres actifs : ce site · source : retained · exécution · couverture partielle · observations actuelles — Modifier`.
Coordinate equality with the configured site identifies `ce site`; other coordinate
filters show `site personnalisé`. Variable, mode and coverage use readable labels.
The default exclusion of replaced observations is explicitly shown as
`observations actuelles`; checking the box shows `observations remplacées incluses`.
Clearing optional filters leaves that default population scope visible. Pro retains
`Filtres avancés` and the complete controls. Input, reload, render, site selection
and mode application refresh the summary without changing values or results.
Repeated applications of the already applied mode preserve manually opened or
closed disclosures, while real transitions restore the mode defaults.
Simple empty history wording: `Aucune comparaison disponible pour ces filtres.`

Limit: Simple users can explicitly expand advanced panels. Recovery
errors keep their existing full wording in both modes to preserve guard clarity.


## Review corrections (4 October 2026)

Presentation-only follow-up to 540134ca8c4c6d31ce7b3d97d74bd043fa2dc41b:
active history-filter scope is always visible in Simple; same-mode storage events
preserve manual disclosure choices; empty history uses comparison wording.
Recovery diagnostics (UUID, idempotence, Supersession, projection Outcome) retain
their existing wording and actions pending a separate recovery batch. No recovery
handler or guard was changed. Open-Meteo footer attribution remains shared.

Regression validation: 853 targeted tests passed (Tonight, Field Observation,
Outcome API/UI, Simple/Pro, simplified UX and all history tests). Eight additional
parameterized cases cover provider, population, mode, coverage and coordinate
summaries; combined filters, clearing, mode changes and reload are also covered.
Chrome smoke passed in both modes at 390 and 1280 pixels, including site scope
after history reload, summary access and repeated storage events.

Complete final suite: 4803 passed, 44 existing warnings, with Node available and
local loopback listener access. JavaScript syntax and git diff checks passed.

## Outcome warning and mobile follow-up (4 October 2026)

Outcome consultation now computes its applicable warnings before calling
`renderOutcomeEvaluation(evaluation, warnings)`. The renderer builds a complete
message (warnings, status, variable results and reasons) before deriving and
storing both Simple/Pro wording variants. Toggles only select the complete variant;
they never append warnings. Each new consultation clears the old variants and
recomputes warnings. The existing creation guards are unchanged.

Other Outcome messages (loading, missing evaluation, readback uncertainty,
protocol errors, superseded errors, unavailable comparison, selection and
canonical lineage diagnostics) follow paths that clear the old variants first.
They remain visible in both modes. Exceptional recovery wording remains deferred.

The clickable `#history-filter-summary` uses `min-width: 0` and
`overflow-wrap: anywhere`: normal words retain ordinary wrapping, while
unbroken provider tokens can wrap and leave the full scope and Modifier readable.

Validation: 853 targeted tests passed, with enhanced Node Outcome regressions for
unknown supersession and replaced observations after both wording switches,
disabled creation, a subsequent warning-free evaluation, variable reasons,
unavailable comparison, invalid projection, superseded error and missing result.
Chrome smoke passed with actual consultation and mode toggles at 390/1280 px;
200-character unbroken provider summaries with multiple filters have no dialog
or summary horizontal overflow, and the summary still opens the filter controls.

Full suite: 4803 passed, 44 existing warnings. JavaScript syntax and
`git diff --check` passed.
