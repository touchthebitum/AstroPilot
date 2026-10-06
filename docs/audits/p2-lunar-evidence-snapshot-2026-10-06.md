# P2 — Historical lunar comparison evidence

## Baseline and scope

PR #318 merged on 2026-10-06 at 17:22:49 UTC. Main and origin/main were
synchronized to `7da13bf1c1106c9fa875aa8eb19db8e28c8f5176`.
The principal checkout had no tracked modifications; its untracked `.DS_Store`
and `astropilot.egg-info/` were left alone. Implementation uses a clean isolated
checkout on `fix/p2-lunar-evidence-snapshot`.
The critical stash `223ec1f5904131d726b694655f137670c0ddeb0b` was inspected
read-only and preserved. No pop/apply/drop. No Field Lab files or live stores
were modified. No AQI, lunar thresholds, preference, or ranking algorithms changed.

## Root cause and pipeline

`IntentNightEvidenceBuilder.build` creates field/window geometry at its selected
reference time: illumination, altitude and separation. Composition resolves each
eligible intent through acquisition-intent profile resolution to an exact optical
profile. `LunarContaminationEstimator.estimate` consumes that geometry and the
profile's central wavelength and FWHM, producing a source factor and separate
relative Rayleigh and Mie indices. Pairwise Pareto comparisons feed preference
and the existing non-dominated intent selection.

Previously evidence, resolved profile IDs and estimates remained local to
`compose_acquisition_intent_selection`. Selection and Candidate carried only
identity, eligibility and selection information. Different estimates with the
same winner consequently became indistinguishable in acceptance lineage.

## Snapshot contract, schema 1

`LunarEvidenceSnapshot` is a dedicated frozen/slotted dataclass. It contains:

- The original immutable `IntentNightEvidence`: imaging field ID, actionable
  start/end/duration, reference time and the three existing lunar geometry fields.
- A tuple of `IntentLunarEstimateSnapshot`, sorted by intent ID, for **all**
  successfully compared eligible intents, including dominated alternatives.
  Each entry preserves intent ID, exact resolved profile ID, central wavelength,
  FWHM and the original `LunarContaminationEstimate` (profile ID, source factor,
  Rayleigh index, Mie index).
- Schema version 1; estimator class identifier and explicitly declared algorithm
  version (production: `relative-rayleigh-mie-v1`); comparison contract
  `pareto-rayleigh-mie-v1`, whose fixed tolerances remain 1e-9 relative and 1e-12
  absolute. Custom estimators without a version declared on their class have
  explicit `None`; their version is not inferred from an inherited algorithm.

No score, grade, confidence, priority or weather evidence is manufactured.
`FilterOpticalProfile` remains a separate definition. The two spectral inputs
are copied into historical evidence so future catalogue edits cannot change
what the estimator actually consumed. The snapshot is not a new filter definition.
The indices remain relative estimates, with the estimator's existing physical
limitations; they are not absolute sky brightness or a weighted AQI.

## Transport and boundaries

Composition records the actual estimates already used by the comparisons and
attaches the snapshot with `dataclasses.replace` after the unchanged selection
function returns. No additional estimate or comparison is run for traceability.

`AcquisitionIntentSelection` -> `ProjectSelectionEngine` -> `Candidate` ->
Tonight actionability `MissionInput` -> `MissionAssembler` -> `NightMission`.
At explicit acceptance, `UserSelectionMissionService` copies the selected
historical candidate's snapshot into the mission input, rather than taking
geometry from a fresh evaluation. It rejects a returned mission that loses or
changes that evidence. The complete comparison survives even when the final
mission uses a shorter window or an explicitly chosen compared alternative.
The snapshot window documents comparison time, not final mission duration.

Acceptance lineage schema **10** registers the immutable snapshot and its nested
evidence/estimate types in the existing strict typed codec. Both candidate
lineage and accepted mission preserve the supplied values. Candidate identity
validation runs again on writing because Candidate itself remains mutable.

Public API exposes the complete nested snapshot on Tonight's primary and
alternative responses and accepted/retrieved mission responses. Datetimes use
the existing JSON serializer (UTC may be represented as `Z`); their instants,
precision, geometry and unrounded indices are preserved. UI renderers are unchanged.

## Absence and identity validation

Snapshots require at least two distinct compared intents and complete geometry.
Single eligible intent, no eligible intent, missing profiles or failed evidence
retain `None`. No lunar evidence is built just to enrich a single-intent result.
Incomparable/equivalent comparisons retain all estimates despite lacking a winner.

Validation rejects duplicate intents, unsupported snapshot schema/comparison
contracts, internal resolved-profile/estimate profile mismatches, different field
IDs, a selected intent outside the compared set and a compared set different
from eligible assessments. Mission snapshots require explicit field/intent IDs.
Composition checks the evidence builder's field against the requested field.
Historical validation does not consult today's optical catalogue or redo selection;
it cannot authenticate an externally forged but internally coherent historical
snapshot. There is no cryptographic integrity claim.

Persisted schema **1–9** reads have explicit `None` on Candidate, MissionInput and
NightMission, without inference, recalculation or destructive migration. Current
writes include an explicit null when proof is absent. Existing legacy validations
remain otherwise unchanged. Legacy test fixtures generated by the current writer
are explicitly stripped of the additive snapshot field before old-version reads;
strict field validation is retained.

## Validation

Tests first reproduced the absent snapshot with three failing regressions.
New coverage checks same winner/different estimates; both Ha and OIII profiles;
all compared alternatives; incomparable selection; single-intent absence;
immutable values; candidate/mission input/mission typed round-trips; full disk
aggregate round-trip; exact API data on primary, alternative and accepted mission;
legacy v9 absence; field/intent/profile corruption; unchanged candidate ranking;
shortened mission window retaining comparison evidence; authoritative historical
acceptance and rejection of a replaced snapshot.

500 focused tests passed. The expanded suite initially exposed expected additive
schema assertions plus sandbox loopback and missing Node limitations. Assertions
were updated for the explicit new contract; the final relevant suite runs with
Node and local loopback available. No Field Lab test or source file was edited.
Final expanded suite: **4699 passed in 27.20 s**, no failures or skips.
`git diff --check` clean.

## Files

Production: `astro_score.py`, `astropilot/app.py`,
`decision/acceptance_lineage_persistence.py`,
`decision/engines/project_selection_engine.py`,
`decision/mission/{mission_input,night_mission,mission_assembler}.py`,
`decision/models/{acquisition_intent_selection,candidate,lunar_evidence_snapshot}.py`,
`decision/services/{acquisition_intent_composition,lunar_contamination_estimator,
tonight_application_service,tonight_response,user_selection_mission}.py`.
Tests: API Tonight/E2E/alternative schema; architecture composition, acceptance
lineage persistence, mission assembler, response and productivity schema assertions.

Recommendation: merge only after required CI checks pass on the exact PR SHA.
No automatic merge.
