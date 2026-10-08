"""Production-authorized input for tests of downstream physical invariants."""
from dataclasses import replace
import astro_score


def authorized_input(value):
    if value.window_start is None or value.window_end is None:
        return value
    field_id = value.imaging_field_id or "sh2-129_ou4"
    intent_id = value.acquisition_intent_id or "sh2-129_ha"
    # Preserve explicit invalid identity for tests of rejection.
    if field_id != "sh2-129_ou4" or intent_id not in ("sh2-129_ha", "ou4_oiii"):
        return value
    project = {"imaging_field_id": field_id,
        "acquisition_intent_targets": [{"acquisition_intent_id": intent_id, "target_hours": 50}],
        "acquisition_intent_progress": [{"acquisition_intent_id": intent_id, "acquired_duration_manual": 0}]}
    modern = astro_score.build_mission_input({"catalog_key": "Sh2-129",
        "selected_acquisition_intent_id": intent_id,
        "window": {"start": value.window_start, "end": value.window_end}},
        profile={"active_equipment": "samyang_183", "projects": {"Sh2-129": project}})
    return replace(value, imaging_field_id=field_id, acquisition_intent_id=intent_id,
        acquisition_capacity=modern.acquisition_capacity,
        creation_authorization=modern.creation_authorization)
