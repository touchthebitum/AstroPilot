# Acquisition intent and selected filter contract

Audit baseline: main c6c41771045ef39b2c5fb7321142ef5ca3d51d75 (2026-10-06).
The P2 reported after PR #280 is already corrected by PR #281, commit
38e8bcaf42a509ca5a210d6f6dab4580a17dcccc. This change locks down that contract
with symmetric regression and Tonight composition tests; no production change
is necessary for the reported divergence.

## Authority and boundaries

The acquisition intent resolved within its imaging field defines the required
`filter_type`. The legacy filter inventory and its heuristic selection are
non-authoritative. `astro_score.build_mission_input` reconciles their optional
hardware description against that required type before creating `MissionInput`.
It preserves a compatible selected object, otherwise uses the first inventory
entry with the required type, otherwise returns `None`. This is justified by the
explicit intent; it does not change intent, invent a filter or resolve an optical
profile. `MissionAssembler`, user selection acceptance and new lineage writes
REJECT a remaining mismatch with `selected_filter_intent_mismatch`.

| Case | Result |
| --- | --- |
| Ha intent + OIII hardware | Input builder uses inventory Ha or None; downstream mismatch is REJECT |
| OIII intent + Ha hardware | Input builder uses inventory OIII or None; downstream mismatch is REJECT |
| Same type, different bandwidth/name | Preserve exact selected object and metadata |
| No matching hardware / empty inventory | None, no fictitious filter; setup capability/intent eligibility remains authoritative |
| Compatible user default | Preserve object and source |
| Incompatible user default | Cannot override intent; same reconciliation/REJECT rules |
| Unknown intent in imaging field | Resolver REJECT; no default authorization |
| Legacy mission without intent identity | Existing compatibility behavior retained |

`FilterOpticalProfile` is a separate typed definition resolved from setup profile
references. Multiple profiles of the same type remain AMBIGUOUS in that resolver;
this contract does not rank profiles or infer profile identity from bandwidth.
No new DEGRADE, NEUTRAL_DEFAULT or USER_DEFAULT policy is introduced. Absence of
a legacy hardware description is not evidence of absent setup capability.
Evidence, confidence, status and priority are unchanged.

## Persistence and scope

Mission dataclasses intentionally allow faithful historical reconstruction.
Existing v8/v9 read tests preserve even historically inconsistent filter metadata;
new writes and operational assembly reject it. Constructor validation would break
that established historical contract, so it is not added here. Partial legacy
identity cannot prove filter consistency; no stronger guarantee is claimed for it.

The tests exercise both divergence directions, explicit default rejection,
compatible metadata preservation and the real input builder through Tonight
service and mission assembler. Optical profile resolution tests separately cover
its authority. Field Lab, lunar contamination, actionability and project completion
are outside this change.
