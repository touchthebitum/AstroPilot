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
recovery diagnostic wording, advanced-filter active-state summary. This batch
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

Limit: Simple users can explicitly expand advanced panels. Advanced filters
remain active when the panel closes; no filter is silently reset. Recovery
errors keep their existing full wording in both modes to preserve guard clarity.
