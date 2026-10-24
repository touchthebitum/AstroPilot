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

for identity, name, purpose, advice, source in (
    ("ngc7000", "North America", "Faire ressortir les nuages d’hydrogène et leurs zones sombres.",
     "Une grande nébuleuse pour apprendre le cadrage, le suivi et l’empilement. Le filtre Hα produit une image monochrome ; la couleur demande d’autres acquisitions.",
     "https://esahubble.org/images/heic0510a/"),
    ("m42", "la nébuleuse d’Orion", "Photographier le gaz lumineux autour des jeunes étoiles d’Orion.",
     "Une nébuleuse lumineuse pour progresser. Son cœur est beaucoup plus brillant que ses extensions : vérifiez qu’il n’est pas saturé et adaptez vos poses. Avec le Hα, le résultat est monochrome. Le ciel, le suivi et le traitement restent déterminants.",
     "https://eso.org/public/images/eso1723a/"),
    ("sh2-190", "la nébuleuse du Cœur", "Photographier les contours de la grande région de gaz Sh2-190, autour de l’amas IC 1805.",
     "Laissez de la place autour de la nébuleuse et vérifiez le cadrage avec votre appareil. Ses extensions sont plus discrètes que son centre. En Hα, l’image reste monochrome ; la couleur demande d’autres acquisitions. L’Âme est un projet distinct, même si la vignette montre les deux régions.",
     "https://www.nebulaphotos.com/ngc-ic/ic1805/"),
    ("sh2-199", "la nébuleuse de l’Âme", "Photographier la région de gaz Sh2-199 associée à IC 1848, avec ses contours et ses zones sombres.",
     "Cherchez la forme de la grande nébuleuse plutôt que les petits détails de ses piliers. En Hα, l’image reste monochrome ; le contraste dépend du ciel et de l’empilement. Le Cœur est un projet distinct, même si la vignette montre les deux régions.",
     "https://www.nebulaphotos.com/ngc-ic/ic1805/"),
    ("rosette", "la Rosette", "Photographier la couronne de gaz autour de l’amas central.",
     "Travaillez la mise au point sur les étoiles et le contraste de la nébuleuse. Le filtre Hα produit une image monochrome ; la couleur demande d’autres acquisitions.",
     "https://www.eso.org/public/images/b12/"),
):
    PROJECT_GUIDANCE[identity] = {"summary": "Un projet Hα pour découvrir " + name + ". Le ciel, le suivi et le traitement restent déterminants.",
        "source_url": source, "source_label": "Découvrir cette nébuleuse et la source de son image"}
    INTENT_GUIDANCE[(identity, identity + "_ha")] = {
        "difficulty": "Pour progresser · nébuleuse étendue",
        "purpose": purpose + " Le filtre Hα isole l’émission de l’hydrogène.", "advice": advice}


from decision.definitions.production_extended_targets import EXTENDED_HA_TARGETS

for target in EXTENDED_HA_TARGETS:
    identity = target["identity"]
    PROJECT_GUIDANCE[identity] = {"summary": target["advice"],
        "source_url": target["source_url"], "source_label": "Source de la photographie de référence"}
    INTENT_GUIDANCE[(identity, identity + "_ha")] = {
        "difficulty": target["difficulty"],
        "purpose": "Photographier l’émission de l’hydrogène de " + target["name"] + " avec le filtre Hα.",
        "advice": target["advice"] + " En Hα, le résultat est monochrome. Le ciel, le suivi et le traitement restent déterminants."}


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
            "discovery_supported": field.imaging_field_id in ({"ngc7000", "rosette", "m42", "sh2-190", "sh2-199"} | {t["identity"] for t in EXTENDED_HA_TARGETS}),
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
