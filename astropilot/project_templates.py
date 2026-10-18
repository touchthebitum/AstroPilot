"""Explicit supported project choices; never infer filter ownership or fields."""
from astropilot.catalog import CATALOG
from decision.definitions.production_imaging_fields import (
    CELESTIAL_OBJECT_DEFINITIONS, IMAGING_FIELD_DEFINITIONS,
)
from decision.definitions.production_setup_filter_capabilities import SETUP_FILTER_CAPABILITIES
from decision.definitions.production_filter_optical_profiles import FILTER_OPTICAL_PROFILES


def project_templates() -> list[dict]:
    objects = {item.celestial_object_id: item for item in CELESTIAL_OBJECT_DEFINITIONS}
    profiles = {item.filter_profile_id: item for item in FILTER_OPTICAL_PROFILES}
    result = []
    for field in IMAGING_FIELD_DEFINITIONS:
        keys = [objects[item.celestial_object_id].canonical_name
                for item in field.components
                if item.celestial_object_id in objects
                and objects[item.celestial_object_id].canonical_name in CATALOG]
        if len(keys) != 1:
            continue  # No unambiguous catalog association: no guessed choice.
        result.append({
            "catalog_key": keys[0], "imaging_field_id": field.imaging_field_id,
            "display_name": field.display_name,
            "acquisition_intents": [
                {"acquisition_intent_id": intent.acquisition_intent_id,
                 "label": intent.label, "filter_type": intent.filter_type,
                 "supported_filters": [
                     {"equipment_id": setup.equipment_id, "filter_profile_id": profile_id,
                      "label": profile_id.replace("_" + str(profiles[profile_id].fwhm_nm).replace(".", "_") + "nm", "").replace("_", " ").title(),
                      "fwhm_nm": profiles[profile_id].fwhm_nm}
                     for setup in SETUP_FILTER_CAPABILITIES
                     for profile_id in setup.available_filter_profile_ids
                     if profile_id in profiles and profiles[profile_id].filter_type == intent.filter_type
                 ]}
                for intent in field.acquisition_intents
            ],
        })
    return result
