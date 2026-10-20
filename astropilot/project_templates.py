"""Explicit supported project choices; never infer filter ownership or fields."""
from astropilot.catalog import CATALOG
from decision.definitions.production_imaging_fields import (
    CELESTIAL_OBJECT_DEFINITIONS, IMAGING_FIELD_DEFINITIONS,
)
from decision.definitions.production_setup_filter_capabilities import SETUP_FILTER_CAPABILITIES
from decision.definitions.production_filter_optical_profiles import FILTER_OPTICAL_PROFILES

# Editorial help, keyed to exact production identities. It does not rank tonight's
# candidates, certify filter ownership or set integration goals.
PROJECT_GUIDANCE = {
    "sh2-129_ou4": {
        "summary": "Pour commencer dans ce champ, privilégiez Sh2-129 en Hα. Ou4 en OIII est un défi pour plus tard. Ces deux nébuleuses restent des cibles exigeantes.",
        "source_url": "https://science.nasa.gov/image-article/apod-2022-october-12-ou4-the-giant-squid-nebula/",
        "source_label": "Comprendre Sh2-129 et Ou4 · NASA",
    },
}
INTENT_GUIDANCE = {
    ("sh2-129_ou4", "sh2-129_ha"): {
        "difficulty": "Exigeant · premier choix dans ce champ",
        "purpose": "Photographier la nébuleuse Sh2-129. Le filtre Hα isole la lumière émise par son hydrogène.",
        "advice": "Commencez par ce filtre pour travailler la mise au point, le suivi et l’empilement. Ce choix est plus accessible que Ou4 en OIII, mais le résultat dépend aussi du ciel et du traitement.",
    },
    ("sh2-129_ou4", "ou4_oiii"): {
        "difficulty": "Très difficile · à réserver pour plus tard si vous débutez",
        "purpose": "Rechercher Ou4, la nébuleuse du Calamar. Le filtre OIII isole la lumière de son oxygène ionisé.",
        "advice": "Ou4 est extrêmement faible. Un filtre adapté ne suffit pas à la rendre facile : prévoyez un projet sur plusieurs nuits, avec un ciel favorable et un traitement soigné. Vous pouvez commencer par Sh2-129 en Hα dans le même champ.",
    },
}


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
            **({"guidance": dict(PROJECT_GUIDANCE[field.imaging_field_id])}
               if field.imaging_field_id in PROJECT_GUIDANCE else {}),
            "acquisition_intents": [
                {"acquisition_intent_id": intent.acquisition_intent_id,
                 "label": intent.label, "filter_type": intent.filter_type,
                 **({"guidance": dict(INTENT_GUIDANCE[(field.imaging_field_id, intent.acquisition_intent_id)])}
                    if (field.imaging_field_id, intent.acquisition_intent_id) in INTENT_GUIDANCE else {}),
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
