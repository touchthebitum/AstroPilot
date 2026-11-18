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
        "difficulty": "Une grande nébuleuse à photographier en plusieurs séances.",
        "purpose": purpose + " Le filtre Hα isole l’émission de l’hydrogène.", "advice": advice + " Elle occupe une grande zone du ciel. Accumuler davantage de photos conservées permet de mieux faire ressortir les détails."}


# Rosette emissions documented by NASA APOD (2024-02-09); no duration is inferred.
PROJECT_GUIDANCE["rosette"] = {
    "summary": "La Rosette peut être photographiée en Hα, OIII et SII. Chaque filtre constitue une acquisition distincte ; une image couleur demande de les assembler au traitement.",
    "source_url": "https://science.nasa.gov/image-article/apod-2024-february-9-when-roses-arent-red/",
    "source_label": "Hydrogène, oxygène et soufre dans la Rosette · NASA",
}
for suffix, element in (("oiii", "oxygène doublement ionisé"), ("sii", "soufre ionisé")):
    INTENT_GUIDANCE[("rosette", "rosette_" + suffix)] = {
        "difficulty": "Une acquisition complémentaire à évaluer sur vos premières images.",
        "purpose": "Photographier l’émission de l’" + element + "." if suffix == "oiii" else "Photographier l’émission du soufre ionisé.",
        "advice": "Ce filtre fournit une image monochrome distincte du Hα. Les acquisitions peuvent être combinées au traitement pour une image couleur. Cette bêta ne propose pas encore de durée de départ pour ce filtre ; le conseil Hα ne s’y applique pas.",
    }


from decision.definitions.production_extended_targets import EXTENDED_HA_TARGETS

for target in EXTENDED_HA_TARGETS:
    identity = target["identity"]
    PROJECT_GUIDANCE[identity] = {"summary": target["advice"],
        "source_url": target["source_url"], "source_label": "Source de la photographie de référence"}
    INTENT_GUIDANCE[(identity, identity + "_ha")] = {
        "difficulty": target["difficulty"],
        "purpose": "Photographier l’émission de l’hydrogène de " + target["name"] + " avec le filtre Hα.",
        "advice": target["advice"] + " En Hα, le résultat est monochrome. Le ciel, le suivi et le traitement restent déterminants."}


# Editorial starting ranges, not measured averages or a calibrated exposure model.
# References are acquisition examples; equipment, sky and processing differ.
EXPOSURE_GUIDANCE = {
    "ngc7000_ha": {
        "min_hours": 2, "max_hours": 4, "suggested_hours": 3,
        "basis": "editorial_starting_point", "filter_type": "Ha",
        "sources": [{"label": "HellaNebula : NGC 7000, 1 h 30 en Hα, 135 mm, Bortle 5",
                     "url": "https://www.hellanebula.com/gallery/coast-yttf2"}],
        "note": "Repère de départ choisi pour apprendre, inspiré d’un exemple publié ; ce n’est pas une moyenne. La durée dépend aussi de votre matériel, du ciel et du traitement. Aucun réglage automatique selon Bortle ou la météo.",
    },
    "m42_ha": {
        "min_hours": 2, "max_hours": 4, "suggested_hours": 3,
        "basis": "editorial_starting_point", "filter_type": "Ha",
        "sources": [{"label": "Starry Wonders : M42 en Hα, 3 h 30",
                     "url": "https://www.starrywonders.com/m42stlha.html"}],
        "note": "Repère de départ, pas une moyenne ni une prévision pour votre matériel et votre ciel. Le cœur d’Orion peut saturer : vérifiez vos images et prévoyez aussi des poses plus courtes si nécessaire.",
    },
    "rosette_ha": {
        "min_hours": 4, "max_hours": 8, "suggested_hours": 6,
        "basis": "editorial_starting_point", "filter_type": "Ha",
        "sources": [
            {"label": "Starry Wonders : Rosette en Hα, 4 h",
             "url": "https://www.starrywonders.com/rosettestl.html"},
            {"label": "Astronewton : Hα seul, 8 h 10, autres filtres séparés",
             "url": "https://www.astronewton.com/rosette-nebula"},
        ],
        "note": "Fourchette de départ inspirée d’exemples publiés avec d’autres matériels. Ce n’est pas une moyenne ni une prévision personnalisée. La lumière du ciel, le suivi et le traitement changent le résultat.",
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
            "discovery_supported": field.imaging_field_id in ({"ngc7000", "rosette", "m42", "sh2-190", "sh2-199"} | {t["identity"] for t in EXTENDED_HA_TARGETS}),
            **({"guidance": dict(PROJECT_GUIDANCE[field.imaging_field_id])}
               if field.imaging_field_id in PROJECT_GUIDANCE else {}),
            "acquisition_intents": [
                {"acquisition_intent_id": intent.acquisition_intent_id,
                 "label": intent.label, "filter_type": intent.filter_type,
                 **({"exposure_guidance": EXPOSURE_GUIDANCE[intent.acquisition_intent_id]}
                    if intent.acquisition_intent_id in EXPOSURE_GUIDANCE and intent.filter_type == "Ha" else {}),
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
