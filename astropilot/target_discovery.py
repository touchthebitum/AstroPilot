"""Read-only physical preselection. No project, mission, goal or credit is created."""
from math import isfinite

from astropilot.project_templates import project_templates
from astropilot.target_catalogue import canonical_target, equipment_catalogue
from decision.services.candidate_assessment import CandidateAssessment, CandidateViabilityEvaluator
from decision.services.session_availability_windowing import select_physical_productive_window
from decision.services.tonight_application_service import _select_forecast_night
from decision.weather.provider_reliability import WeatherLocation

# Curated reference images; never use a source photograph as framing evidence.
TARGET_IMAGES = {
    "NorthAmerica": {
        "src": "/ui/target-north-america.jpg",
        "source_url": "https://esahubble.org/images/heic0510a/",
        "credit": "Davide De Martin (ESA/Hubble), the ESA/ESO/NASA Photoshop FITS Liberator & Digitized Sky Survey 2",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    },
    "M42": {
        "src": "/ui/target-orion.jpg",
        "source_url": "https://eso.org/public/images/eso1723a/",
        "credit": "ESO/G. Beccari",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "note": "Vue professionnelle de la région centrale d’Orion, plus serrée que votre champ au 135 mm. Cette image combine plusieurs filtres ; elle ne prédit ni votre cadrage ni votre résultat en Hα.",
    },
    "IC1805": {
        "src": "/ui/target-heart-soul-ha.jpg",
        "alt": "Cœur en haut à droite et Âme en bas à gauche · photographie Hα de Nico Carver",
        "source_url": "https://www.nebulaphotos.com/ngc-ic/ic1805/",
        "credit": "IC1805 and IC1848 by Nico Carver",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "license_label": "CC BY-SA 4.0",
        "note": "Photo Hα en noir et blanc montrant le Cœur et l’Âme ensemble. Le Cœur est en haut à droite ; ce choix concerne seulement cette région (Sh2-190). L’image a été obtenue avec un autre matériel ; elle ne prédit ni votre cadrage ni votre résultat.",
    },
    "IC1848": {
        "src": "/ui/target-heart-soul-ha.jpg",
        "alt": "Cœur en haut à droite et Âme en bas à gauche · photographie Hα de Nico Carver",
        "source_url": "https://www.nebulaphotos.com/ngc-ic/ic1805/",
        "credit": "IC1805 and IC1848 by Nico Carver",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "license_label": "CC BY-SA 4.0",
        "note": "Photo Hα en noir et blanc montrant le Cœur et l’Âme ensemble. L’Âme est en bas à gauche ; ce choix concerne seulement cette région (Sh2-199). L’image a été obtenue avec un autre matériel ; elle ne prédit ni votre cadrage ni votre résultat.",
    },
    "Rosette": {
        "src": "/ui/target-rosette.jpg",
        "source_url": "https://www.eso.org/public/images/b12/",
        "credit": "ESO/S. Brunier",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    },
}


def discover_targets(*, inputs, profile, weather, weather_freshness,
                     reference_time_utc, confirmed_filter_profile_ids, forecast=None):
    if inputs.availability is None:
        raise ValueError("discovery_availability_required")
    templates = project_templates()
    supported = {item["filter_profile_id"] for template in templates
                 for intent in template["acquisition_intents"]
                 for item in intent["supported_filters"]
                 if item["equipment_id"] == inputs.equipment}
    confirmed = set(confirmed_filter_profile_ids)
    if not confirmed or not confirmed <= supported:
        raise ValueError("discovery_filter_confirmation_required")
    catalogue = equipment_catalogue(profile=profile, equipment_id=inputs.equipment,
                                   confirmed_filter_profile_ids=confirmed)
    material_matches = {item["key"]: item for item in catalogue["targets"]}
    # An empty portfolio is intentional for ranking: discovery must be independent
    # of saved goals and accumulated exposure. The original profile stays untouched.
    effective = {**profile, "projects": {}, "sessions": [],
                 "location": inputs.location, "active_equipment": inputs.equipment,
                 "available_equipment": [inputs.equipment]}
    if forecast is None:
        from astro_score import forecast_astro
        forecast = forecast_astro
    run = forecast(inputs.location["latitude"], inputs.location["longitude"],
                   inputs.location["name"], inputs.bortle, target="deep_sky", goal="nebulae",
                   weather=weather, profile=effective, reference_time_utc=reference_time_utc,
                   availability=inputs.availability)
    if run is None:
        raise ValueError("forecast_unavailable")
    night = _select_forecast_night(run.nights, inputs.availability, weather) if run.nights else None
    suggestions = []
    if night:
        from astro_score import build_mission_input
        evaluations = {item["catalog_key"]: item for item in night["all_objects"]}
        for template in templates:
            key = template["catalog_key"]
            evaluation = evaluations.get(key)
            if key not in TARGET_IMAGES or not evaluation:
                continue
            material = material_matches.get(key)
            if not material or material["framing"]["status"] != "nominal_fit":
                continue
            score = evaluation.get("global_score", evaluation.get("score"))
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score) or score <= 0:
                continue
            assessment = CandidateAssessment.build_for_catalog_key(
                catalog_key=key, object_evaluations=evaluations, profile=effective,
                weather_snapshot=weather, weather_freshness=weather_freshness,
                decision_location=WeatherLocation(latitude=inputs.location["latitude"], longitude=inputs.location["longitude"]),
                build_mission_input=lambda evaluation, *, profile: build_mission_input(evaluation, profile=profile, for_intent_selection=True))
            if not CandidateViabilityEvaluator.is_viable(assessment):
                continue
            window = select_physical_productive_window(assessment.productive_window, inputs.availability)
            if window is None:
                continue
            # Catalogue aliases identify an already saved project without migrating
            # its key or overwriting progress. Ambiguous legacy duplicates are not
            # resolved by guessing which project the operator meant.
            existing_keys = [saved_key for saved_key in profile.get("projects", {})
                             if (target := canonical_target(saved_key)) is not None
                             and target.key == key]
            if len(existing_keys) > 1:
                continue
            existing_key = existing_keys[0] if existing_keys else None
            for intent in template["acquisition_intents"]:
                matches = [item for item in intent["supported_filters"]
                           if item["equipment_id"] == inputs.equipment and item["filter_profile_id"] in confirmed]
                if len(matches) != 1:
                    continue
                optical_match = next((item for item in material["confirmed_filters"]
                    if item["filter_profile_id"] == matches[0]["filter_profile_id"]), None)
                if not optical_match or optical_match["status"] != "documented_match":
                    continue
                suggestions.append({
                    "catalog_key": key, "display_name": template["display_name"],
                    "imaging_field_id": template["imaging_field_id"],
                    "acquisition_intent_id": intent["acquisition_intent_id"],
                    "filter": matches[0], "filter_type": intent["filter_type"],
                    "guidance": intent["guidance"], "image": TARGET_IMAGES[key],
                    "equipment_match": {"geometry": catalogue["geometry"],
                        "framing": material["framing"], "filter": optical_match,
                        "extent_arcmin": material["extent_arcmin"], "extent_scope": material["scope"]},
                    "window_start": window.window_start.isoformat(), "window_end": window.window_end.isoformat(),
                    "already_saved": existing_key is not None,
                    "existing_project_key": existing_key, "_score": score,
                })
    suggestions.sort(key=lambda item: (-item["_score"], item["catalog_key"]))
    for item in suggestions:
        del item["_score"]
    return {"status": "suggestions" if suggestions else "no_suggestion", "suggestions": suggestions[:3],
            "catalogue": catalogue,
            "scope": f"Catalogue étendu : {catalogue['extended_catalogue']['records']} fiches, dont {len(catalogue['targets'])} cibles étudiées. La présélection automatique de cette bêta reste limitée à North America, la Rosette, Orion (M42), le Cœur et l’Âme en Hα, avec cadrage et filtre vérifiés. Une fiche de référence ne constitue pas à elle seule une mission.",
            "notice": "Le créneau est une estimation selon les prévisions. Confirmez votre projet, puis relancez l’analyse avant de sortir. Aucun temps de pose n’est enregistré.",
            "weather_retrieved_at": weather.retrieved_at_utc.isoformat()}
