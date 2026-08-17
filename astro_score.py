
import math
import json
import requests
import warnings
import copy
from dataclasses import replace
from decision.services.tonight_mission_service import (
    TonightMissionService,
)
from decision.opportunity.opportunity_engine import OpportunityEngine
from decision.recommendation.recommendation_engine import (
    RecommendationEngine,
)
from decision.services.opportunity_recommendation_service import (
    OpportunityRecommendationService,
)
from decision.portfolio.project_state import (
    project_state,
    project_progress,
    project_remaining_hours,
)
from decision.portfolio.project_scoring import (
    project_priority,
    project_roi,
    closure_bonus,
    progression_bonus,
    simulated_portfolio_score,
)
from decision.portfolio.project_gain import (
    marginal_gain_factor,
    portfolio_gain_if_shot,
    session_portfolio_gain,
)
from decision.portfolio.diversification import (
    diversification_bonus,
    portfolio_category_load,
)
from decision.season.season_engine import SeasonEngine
from astropilot.equipment_catalog import EQUIPMENT_PROFILES
from decision.portfolio.portfolio_engine import PortfolioEngine
from decision.forecast.forecast_engine import ForecastEngine
from decision.runners.tonight_runner import TonightRunner
from decision.portfolio.portfolio_forecast_engine import PortfolioForecastEngine
from decision.runners.report_runner import ReportRunner
from decision.engines.night_strategy_engine import NightStrategyEngine
from decision.engines.project_selection_engine import ProjectSelectionEngine
from decision.portfolio.portfolio_presenter import (show_portfolio_completion_forecast,)
from decision.rules.object_fit_rule import ObjectFitRule
from datetime import datetime, timedelta
from decision.models.context.decision_context import DecisionContext
from decision.models.context.session_context import SessionContext
from decision.models.context.site_context import SiteContext
from decision.models.context.weather_context import WeatherContext
from decision.models.context.sky_context import SkyContext
from decision.models.context.equipment_context import EquipmentContext
from decision.models.context.portfolio_context import PortfolioContext
from decision.models.context.preferences_context import PreferencesContext
from decision.models.sky.celestial_object import CelestialObject
from decision.models.equipment.camera import Camera
from decision.models.equipment.mount import Mount
from decision.models.equipment.imaging_optics import ImagingOptics
from decision.models.equipment.imaging_filter import ImagingFilter
from decision.models.equipment.imaging_setup import ImagingSetup
from decision.rules.image_quality_rule import ImageQualityRule
from decision.rules.resolution_rule import ResolutionRule
from decision.rules.sampling_rule import SamplingRule
from decision.rules.wind_rule import WindRule
from decision.rules.humidity_rule import HumidityRule
from decision.rules.cloud_rule import CloudRule
from decision.rules.moon_rule import MoonRule
from decision.decision_engine import DecisionEngine
from decision.rules.altitude_rule import AltitudeRule
from decision.rules.visibility_rule import VisibilityRule
from decision.rules.seeing_rule import SeeingRule
from decision.mission.mission_builder import NightMissionBuilder
from decision.mission.mission_input import MissionInput
from decision.mission.mission_presenter import MissionPresenter
from decision.weather.weather_forecast import WeatherForecast
from decision.engines.future_opportunity_engine import FutureOpportunityEngine
from zoneinfo import ZoneInfo
from astral import LocationInfo
from astral.sun import sun
from astral.moon import phase as moon_phase
from astropy.coordinates.baseframe import NonRotationTransformationWarning
from astropilot.catalog import CATALOG
from astropilot.user_profile import (
    get_projects,
)

import argparse
from astropilot.user_profile import (
    get_default_location,
    load_user_profile,
    get_active_equipment,
)

warnings.filterwarnings(
    "ignore",
    category=NonRotationTransformationWarning
)

TIMEZONE = "Europe/Zurich"

TARGET = "deep_sky"

TARGET_OBJECTS = {
    key: {
        "ra": value["ra"],
        "dec": value["dec"],
        "size_arcmin":
value.get("size_arcmin",
value.get("width_arcmin", 30)),
    }
    for key, value in CATALOG.items()
    if "ra" in value and "dec" in value
}

OBJECT_SIZES = {
    "M31": 140,
    "M42": 85,
    "M51": 11,
    "M81": 27,
    "M101": 28,
    "Rosette": 80,
    "NorthAmerica": 120,
    "Pelican": 60,
    "IC1396": 170,
    "Heart": 120,
    "Soul": 150,
    "Veil": 180,
}

TARGETS = {
    "milky_way": {
        "moon": 3.5,
        "cloud": 1.5,
        "humidity": 1.2,
        "precip": 1.2,
        "wind": 0.5,
        "visibility": 0.7,
        "bortle": 0.5,
    },
    "deep_sky": {
        "moon": 2.0,
        "cloud": 1.5,
        "humidity": 0.5,
        "precip": 1.8,
        "wind": 0.4,
        "visibility": 0.6,
        "bortle": 1.0,
    },
    "planetary": {
        "moon": 0.2,
        "cloud": 1.5,
        "humidity": 0.5,
        "precip": 1.0,
        "wind": 0.8,
        "visibility": 0.5,
        "bortle": 0.1,
    },
    "moon": {
        "moon": 0.0,
        "cloud": 1.4,
        "humidity": 0.4,
        "precip": 1.0,
        "wind": 0.6,
        "visibility": 0.3,
        "bortle": 0.0,
        
    },
    "nightscape": {
    "moon": 0.8,
    "cloud": 1.2,
    "humidity": 0.8,
    "precip": 1.0,
    "wind": 0.6,
    "visibility": 0.7,
    "bortle": 0.4,
},
}

def forecast_night_capacities(
    lat,
    lon,
    days=14,
    weather=None,
):
    if weather is None:
        weather = fetch_weather(lat, lon)
    if not weather:
        return []

    hourly = parse_hourly_weather(weather)

    from decision.weather.weather_forecast import WeatherForecast

    forecast = WeatherForecast(
    hourly=hourly,
    hourly_clouds=[h.get("cloud_cover", 100) for h in hourly],
    hourly_humidity=[h.get("relative_humidity_2m", 100) for h in hourly],
    hourly_wind=[h.get("wind_speed_10m", 0) for h in hourly],
    hourly_temperature=[h.get("temperature_2m", 0) for h in hourly],
    hourly_visibility=[h.get("visibility", 10000) for h in hourly],
)

    nights = {}

    for h in hourly:
        
        hour = h["time"].hour

        if hour < 22 and hour > 4:
            continue

        date = h["time"].date().isoformat()

        cloud = h.get("cloud_cover", 100)
        humidity = h.get("relative_humidity_2m", 100)

        score = 100

        score -= cloud * 0.6
        score -= max(0, humidity - 70) * 0.3

        score = max(0, score)

        if score >= 80:
            hours = 6.0
        elif score >= 60:
            hours = 4.0
        elif score >= 40:
            hours = 2.0
        elif score >= 20:
            hours = 1.0
        else:
            hours = 0.0

        if date not in nights:
            nights[date] = {
                "date": date,
                "quality": score,
                "hours": hours
            }
        else:
            nights[date]["quality"] = max(
                nights[date]["quality"],
                score
            )

            nights[date]["hours"] = max(
                nights[date]["hours"],
                hours
            )

    return list(nights.values())[:days]


def fetch_weather(lat: float, lon: float) -> dict | None:
    url = "https://api.open-meteo.com/v1/forecast"
    #url = "https://api.open-meteo.com_BUG/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": TIMEZONE,
        "forecast_days": 7,
        "hourly": ",".join([
                "cloud_cover",
                "cloud_cover_low",
                "cloud_cover_mid",
                "cloud_cover_high",
                "precipitation",
                "relative_humidity_2m",
                "visibility",
                "wind_speed_10m",
                "temperature_2m",
            ])
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.ReadTimeout:
        print("Erreur météo : timeout Open-Meteo")
        return None

    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP Open-Meteo : {e}")
        return None

    except Exception as e:
        print(f"ERREUR : prévisions météo indisponibles ({type(e).__name__})")
        return None

def season_days_remaining(obj):
    return SeasonEngine.season_days_remaining(obj)

def season_urgency_bonus(obj):
    return SeasonEngine.urgency_bonus(obj)


def regret_score(project_name):
    future = future_engine.estimate (project_name)

    good_nights = max(1, future.good_nights)
    remaining = project_remaining_hours(project_name)

    if remaining is None or remaining <= 0:
        return 0

    regret = remaining / good_nights

    return round(min(10, regret), 1)


def show_multi_night_portfolio_roadmap(
    forecast_engine,
    night_capacities=None,
    avg_night_hours=5,
):

    simulated = forecast_engine.simulate_dynamic_portfolio_roadmap(
    night_capacities=night_capacities,
    avg_night_hours=avg_night_hours,
    )

    print("\n===== ROADMAP MULTI-NUITS DYNAMIQUE =====")

    if not simulated:
        print(
            "Tous les projets du portefeuille "
            "sont déjà terminés."
        )
        return

    for step in simulated:
        date_txt = step.get("date")

        if date_txt:
            print(
                f"Nuit {step['night']} ({date_txt}) : "
                f"{step['project']} "
                f"({step['hours']:.1f} h)"
            )
        else:
            print(
                f"Nuit {step['night']} : "
                f"{step['project']} "
                f"({step['hours']:.1f} h)"
            )

        if step["completed"]:
            print(f"✓ {step['project']} terminé")


def season_bonus(obj):
    """
    Bonus saisonnier simple basé sur l'altitude actuelle de l'objet.
    Version provisoire pour valider le pipeline.
    """
    alt = obj.get("altitude", 0)

    if alt >= 70:
        return 15
    elif alt >= 50:
        return 10
    elif alt >= 30:
        return 5
    return 0


def risk_label_to_score(risk):
    mapping = {
        "FAIBLE": 20,
        "MOYEN": 50,
        "ÉLEVÉ": 80,
        "CRITIQUE": 100,
    }

    return mapping.get(str(risk).upper(), 50)

def compute_postponement_impact(
    postponement_risk,
    confidence="MOYENNE",
    project_priority=50,
    astro_score=0,
):
    """
    Convertit le risque de report en impact réel sur le score final.

    Logique :
    - mauvais soir + gros risque => pénalité prudente
    - bon soir + gros risque => bonus d'urgence
    - confiance basse => impact plus fort
    """

    if postponement_risk is None:
        postponement_risk = 0

    risk = max(0, min(float(postponement_risk), 100))
    priority = max(0, min(float(project_priority), 100))

    confidence_factor = {
        "HAUTE": 0.8,
        "MOYENNE": 1.0,
        "BASSE": 1.2,
    }.get(str(confidence).upper(), 1.0)

    priority_factor = 1.0 + priority / 200  # max x1.5

    penalty = 0
    urgency_bonus = 0
    reason = "Risque de report faible ou neutre."

    if risk >= 70 and astro_score >= 70:
        urgency_bonus = risk * 0.10 * priority_factor
        reason = "Bonne nuit et risque de report élevé : bonus d'urgence."
    elif risk >= 70:
        penalty = risk * 0.20 * confidence_factor * priority_factor
        reason = "Risque de report élevé mais conditions insuffisantes : pénalité prudente."
    elif risk >= 40:
        penalty = risk * 0.08 * confidence_factor
        reason = "Risque de report modéré : légère pénalité."
    else:
        penalty = risk * 0.03
        reason = "Risque de report faible : impact minimal."

    net_impact = urgency_bonus - penalty

    return {
        "postponement_penalty": round(penalty, 2),
        "urgency_bonus": round(urgency_bonus, 2),
        "postponement_net_impact": round(net_impact, 2),
        "postponement_reason": reason,
    }

def explain_recommendation(project):
    """
    Génère les raisons principales qui justifient une recommandation.
    Ne modifie pas le score, ne fait qu'expliquer la décision.
    """

    reasons = []

    astro_score = project.get("astro_score", 0)
    roi = project.get("roi", 0)
    postponement_risk = project.get("postponement_risk", 0)
    completion_bonus = project.get("completion_bonus", 0)
    closure_bonus = project.get("closure_bonus", 0)
    season_bonus = project.get("season_bonus", 0)

    if astro_score >= 90:
        reasons.append("Conditions astronomiques excellentes.")
    elif astro_score >= 75:
        reasons.append("Très bonnes conditions astronomiques.")

    if roi >= 1.0:
        reasons.append("Rendement projet élevé pour cette session.")

    if postponement_risk >= 70:
        reasons.append("Risque de report élevé : cette cible ne doit pas être trop repoussée.")
    elif postponement_risk >= 40:
        reasons.append("Risque de report modéré à prendre en compte.")

    if completion_bonus >= 10:
        reasons.append("Cette session apporte une forte progression du projet.")

    if closure_bonus > 0:
        reasons.append("Cette nuit rapproche nettement le projet de sa finalisation.")

    if season_bonus > 0:
        reasons.append("La cible est actuellement dans une période favorable.")

    if not reasons:
        reasons.append("Choix retenu par équilibre global entre conditions, projet et portefeuille.")

    return reasons


def framing_score(setup, project_name):

    object_size = OBJECT_SIZES.get(project_name)

    if not object_size:
        return 0

    focal = setup.get(
        "focal_length_mm",
        setup.get("focal_length", 135),
    )

    sensor_width = setup.get(
        "sensor_width_mm",
        setup.get("sensor_width", 23.5),
    )

    fov_width_deg = 57.3 * sensor_width / focal
    fov_width_arcmin = fov_width_deg * 60

    fill_ratio = object_size / fov_width_arcmin

    if 0.4 <= fill_ratio <= 0.8:
        return 25

    elif 0.2 <= fill_ratio < 0.4:
        return 15

    elif 0.8 < fill_ratio <= 1.0:
        return 15

    elif 1.0 < fill_ratio <= 1.5:
        return 5

    else:
        return -20


def setup_score(setup, project):

    score = 0
    reasons =[]

    focal = setup.get("focal_length_mm", setup.get("focal_length", 135))
    f_ratio = setup.get("f_ratio", 5.6)

    project_type = project.get("type", "")
    if not project_type:
        name = project.get("name", "")
        project_type = CATALOG.get(name, {}).get("type", "")


    if project_type in ["nebula", "nebulae", "supernova_remnant", "emission_nebula"]:
        if focal <= 200:
            score += 20
            reasons.append("Focale idéale pour les grandes nébuleuses")
        elif focal <= 500:
            score += 10
            reasons.append("Focale correcte pour les nébuleuses")
        else:
            score -= 10
            reasons.append("Focale trop longue pour une grande nébuleuse")

    elif project_type in ["galaxy", "galaxies"]:
        if focal >= 400:
            score += 20
            reasons.append("Focale adaptée aux galaxies")
        elif focal >= 200:
            score += 10
            reasons.append("Focale correcte pour les galaxies")
        else:
            score -= 10
            reasons.append("Focale trop courte pour les galaxies")

    score += framing_score(setup, project["name"])

    return {
    "score": score,
    "reasons": reasons,
}

def build_mission_input(evaluation):
    window = evaluation["window"]
    window_start = window["start"]
    window_end = window["end"]
    astronomical_hours = (window_end - window_start).total_seconds() / 3600
    remaining_hours = evaluation.get("remaining_hours")
    recommended_hours = astronomical_hours
    if remaining_hours is not None:
        recommended_hours = min(recommended_hours, max(0, remaining_hours))

    catalog_key = evaluation.get(
        "catalog_key",
        evaluation.get("name"),
    )

    selected_weather = evaluation.get("selected_window_weather")
    if selected_weather is not None:
        selected_weather = replace(
            selected_weather,
            hourly_moon_penalty=[
                min(1.0, max(0.0, value / 35.0))
                for value in selected_weather.hourly_moon_penalty
            ]
            if selected_weather.hourly_moon_penalty is not None
            else None,
        )

    moon_penalty = window.get("moon_penalty")
    if moon_penalty is not None:
        moon_penalty = min(1.0, max(0.0, moon_penalty / 35.0))

    return MissionInput(
        window_start=window_start,
        window_end=window_end,
        astronomical_hours=astronomical_hours,
        weather=selected_weather,
        moon_penalty=moon_penalty,
        recommended_hours=recommended_hours,
        expected_gain=session_portfolio_gain(
            catalog_key,
            recommended_hours,
        ),
    )


def strategy_weights(mode="balanced"):
    """
    Pondérations utilisées par les différentes stratégies
    de décision d'AstroPilot.
    """

    strategies = {

        "balanced": {
            "astro": 1.0,
            "roi": 1.0,
            "report": 1.0,
            "completion": 1.0,
            "diversity": 1.0,
        },

        "roi": {
            "astro": 0.8,
            "roi": 2.0,
            "report": 0.8,
            "completion": 0.7,
            "diversity": 0.5,
        },

        "completion": {
            "astro": 0.8,
            "roi": 0.7,
            "report": 1.0,
            "completion": 2.0,
            "diversity": 0.5,
        },

        "diversification": {
            "astro": 0.8,
            "roi": 0.7,
            "report": 0.8,
            "completion": 0.5,
            "diversity": 2.0,
        },

        "risk": {
            "astro": 0.9,
            "roi": 0.6,
            "report": 2.0,
            "completion": 1.0,
            "diversity": 0.8,
        },
    }

    return strategies.get(mode, strategies["balanced"])

project_selection_engine = ProjectSelectionEngine()

night_strategy_engine = NightStrategyEngine(
    strategy_weights
)


def recommend_project_for_night(top_objects, available_hours=3.0):
    profile = load_user_profile()
    prefs = profile.get("preferences", {})

    astro_weight = prefs.get("astro_weight", 0.7)
    project_weight = prefs.get("project_weight", 0.3)
    decision_mode = prefs.get("decision_mode", "balanced")

    projects = get_projects()
    candidates = []

    for obj in top_objects:
        catalog_key = obj.get("catalog_key", obj.get("name"))

        if catalog_key not in projects:
            continue

        astro_score = obj.get("global_score", obj.get("score", 0))

        if astro_score <= 0:
            continue

        priority = project_priority(catalog_key)
        altitude = 0
        season = 0
        season_urgency = season_urgency_bonus(obj)
        roi = project_roi(catalog_key)

        future = future_engine.estimate (catalog_key)

        risk_label = future.risk

        # Ancien système
        risk_v1 = risk_label_to_score(risk_label)

        # Pour le moment on conserve V1 comme score utilisé
        postponement_risk = risk_v1

        postponement_impact = compute_postponement_impact(
            postponement_risk=postponement_risk,
            confidence=obj.get("confidence", "MOYENNE"),
            project_priority=priority,
            astro_score=astro_score,
        )

        completion_bonus = marginal_gain_factor(project_progress(catalog_key)) * 10
        completion_bonus = min(completion_bonus, 30)

        closure = closure_bonus(catalog_key, available_hours)

        opportunity_ratio = future.opportunity_ratio

        opportunity_bonus = max(
            0,
            min(8, round(8 / max(opportunity_ratio, 0.1), 1))
        )

        regret = regret_score(catalog_key)
        regret_bonus = min(5, regret * 1.2)

        progression = progression_bonus(catalog_key)
        diversity_bonus = diversification_bonus(catalog_key)

        astro_part = astro_score * astro_weight
        project_part = priority * project_weight

        roi_bonus = min(15, roi * 2)


        portfolio_rank_bonus = 0

        portfolio_ranking = sorted(
            projects.keys(),
            key=lambda name: (
                project_roi(name) * 20
                + session_portfolio_gain(name, available_hours)
                + closure_bonus(name, available_hours)
            ),
            reverse=True
        )


        if catalog_key in portfolio_ranking:
            rank = portfolio_ranking.index(catalog_key) + 1

            if rank == 1:
                portfolio_rank_bonus = 12
            elif rank == 2:
                portfolio_rank_bonus = 6
            elif rank == 3:
                portfolio_rank_bonus = 3

        portfolio_bonus = (
            project_part
            + roi_bonus
            + closure
            + completion_bonus
            + opportunity_bonus
            + regret_bonus
            + progression
            + diversity_bonus
            + portfolio_rank_bonus
        )

        final_score = (
            astro_part
            + altitude
            + season
            + season_urgency
            + portfolio_bonus
        + postponement_impact["postponement_net_impact"]
        )

        # Limite l’avantage portefeuille si l’objet est surtout choisi grâce au portefeuille
        if portfolio_bonus > astro_part * 0.5:
            final_score -= portfolio_bonus * 0.3

        remaining = project_remaining_hours(catalog_key)

        if remaining is not None and remaining <= available_hours:
            final_score += 30

        strategy_scores, decision_score = (
        night_strategy_engine.compute_strategy_scores(
            astro_part=astro_part,
            roi_bonus=roi_bonus,
            postponement_net_impact=postponement_impact[
                "postponement_net_impact"
            ],
            completion_bonus=completion_bonus,
            diversity_bonus=diversity_bonus,
            decision_mode=decision_mode,
            fallback_score=final_score,
        )
    )
        acquired_hours = float(
            projects.get(catalog_key, {}).get("hours", 0)
        )
        candidates.append(
            project_selection_engine.build_candidate(
                name=obj["name"],
                catalog_key=catalog_key,
                priority=priority,
                astro_score=astro_score,
                final_score=final_score,
                decision_score=decision_score,
                season_bonus=season,
                altitude_bonus=altitude,
                roi=roi,
                portfolio_score=portfolio_bonus,
                global_score=obj.get("global_score", astro_score),
                setup_score=obj.get("setup_score", 0),
                best_setup=obj.get("best_setup"),
                completion_bonus=completion_bonus,
                closure_bonus=closure,
                postponement_risk=postponement_risk,
                postponement_impact=postponement_impact,
                reasons=explain_recommendation(
                    {
                        "astro_score": astro_score,
                        "roi": roi,
                        "postponement_risk": postponement_risk,
                        "completion_bonus": completion_bonus,
                        "closure_bonus": closure,
                        "season_bonus": season,
                        "progression_bonus": progression,
                        "diversity_bonus": diversity_bonus,
                    }
                ),
                strategy_scores=strategy_scores,
                acquired_hours=acquired_hours,
            )
        )

    if not candidates:
        return None

    candidates = project_selection_engine.rank_candidates(candidates)
    
    return candidates

def forecast_available_hours(nights):
    total = 0

    for night in nights:
        if "hours" in night:
            total += night["hours"]
            continue

        window = night.get("best_window")

        if not window:
            continue

        start = int(window["start"].split(":")[0])
        end = int(window["end"].split(":")[0])

        total += max(0, end - start)

    return round(total, 1)

def estimate_completion_date(hours_needed, nights):
    remaining = hours_needed

    for night in sorted(nights, key=lambda x: x["date"]):

        window = night.get("best_window")

        if not window:
            continue

        start = int(window["start"].split(":")[0])
        end = int(window["end"].split(":")[0])

        available = end - start

        if available <= 0:
            continue

        remaining -= available

        if remaining <= 0:
            return night["date"]

    return "Au-delà des prévisions"

def estimate_portfolio_completion_date(total_remaining, nights):
    remaining = total_remaining

    for night in sorted(nights, key=lambda x: x["date"]):

        window = night.get("best_window")

        if not window:
            continue

        start = int(window["start"].split(":")[0])
        end = int(window["end"].split(":")[0])
        available = end - start

        if available <= 0:
            continue

        remaining -= available

        if remaining <= 0:
            return night["date"]

    return None

def show_roadmap(
    roadmap,
    forecast_engine,
    night_capacities=None,
    ):

    show_multi_night_portfolio_roadmap(
    forecast_engine=forecast_engine,
    night_capacities=night_capacities,
    )

def average_night_capacity(nights):
    if not nights:
        return 1

    return (
        forecast_available_hours(nights)
        / max(1, len(nights))
    )


def portfolio_score(name):
    priority = project_priority(name)
    roi = project_roi(name)

    progress = project_progress(name)
    completion = progress / 5

    closure = closure_bonus(name)

    return (
        priority * 0.6
        + roi * 3
        + completion
        + closure
    )

def show_portfolio_ranking():

    projects = get_projects()

    rows = []

    for name in projects:
        remaining = project_remaining_hours(name)

        if remaining is None or remaining <= 0:
            continue

        priority = project_priority(name)
        roi = project_roi(name)
        progress = project_progress(name)
        closure = closure_bonus(name)

        score = portfolio_score(name)

        rows.append({
            "name": name,
            "score": score,
            "priority": priority,
            "progress": progress,
            "remaining": remaining,
            "roi": roi,
            "closure": closure
        })

    rows.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print("\n===== CLASSEMENT PORTEFEUILLE =====\n")

    for i, r in enumerate(rows, start=1):
        print(
            f"{i}. {r['name']} "
            f"score={r['score']:.1f} "
            f"progress={r['progress']:.1f}% "
            f"reste={r['remaining']:.1f}h "
            f"roi={r['roi']:.2f}"
        )

def show_completion_forecast(nights):

    projects = get_projects()

    roadmap = []

    if not projects:
        return

    best_nights = sorted(
        nights,
        key=lambda x: x["score"],
        reverse=True
    )

    for name in projects:
        progress = project_progress(name)
        remaining = project_remaining_hours(name)

        nights_needed = math.ceil (remaining / 2.0)
        completion_date = estimate_completion_date(
            remaining,
            best_nights
        )

        roadmap.append({
            "name": name,
            "progress": progress,
            "remaining": remaining,
            "nights": nights_needed,
            "completion_date" : completion_date
        })

        roadmap.sort(
            key=lambda x: portfolio_score(x["name"]),
            reverse=True
    )
    print("\n===== ROADMAP ASTRO =====\n")

    for i, p in enumerate(roadmap, start=1):
        print(f"{i}. {p['name']}")
        print(f"   Progression : {p['progress']:.1f} %")
        print(f"   Reste : {p['remaining']:.1f} h")
        print(f"   Fin estimée : {p['completion_date']}")
        print()

    total_remaining = sum(p["remaining"] for p in roadmap)

    portfolio_completion_date = estimate_portfolio_completion_date(
    total_remaining,
    best_nights
)

    print("\n===== OBJECTIF GLOBAL =====\n")
    print(f"Heures restantes : {total_remaining:.1f} h")

    if portfolio_completion_date:
        print(f"Date de fin estimée : {portfolio_completion_date}")
    else:
        print("Date de fin estimée : Au-delà des prévisions")

    print(f"Temps restant portefeuille : {total_remaining:.1f} h")
    avg_capacity = average_night_capacity(best_nights)
    print(f"Nuits restantes estimées : {total_remaining / max(1, avg_capacity):.1f}")


def build_astro_calendar(projects, nights):
    calendar = []

    sorted_nights = sorted(
        nights,
        key=lambda x: x["score"],
        reverse=True
    )

    project_order = []

    for name in projects:
        project_order.append(
            {
                "name": name,
                "score": portfolio_score(name),
                "remaining": project_remaining_hours(name),
            }
        )

    project_order.sort(
        key=lambda x: x["score"],
        reverse=True
    )
    night_index = 0
    for project in project_order:
        remaining = project["remaining"]

        if remaining <= 0:
            continue

        while remaining > 0 and night_index < len(sorted_nights):

            night = sorted_nights[night_index]

            window = night.get("best_window")

            if not window:
                night_index += 1
                continue

            start = int(window["start"].split(":")[0])
            end = int(window["end"].split(":")[0])
            available = end - start

            if available <= 0:
                night_index += 1
                continue

            used = min(available, remaining)

            calendar.append(
                {
                    "date": night["date"],
                    "project": project["name"],
                    "hours": used,
                    "remaining_after": remaining - used,
                }
            )

            remaining -= used
            night_index += 1

    return calendar

def show_astro_calendar(nights):
    projects = get_projects()

    if not projects:
        return

    calendar = build_astro_calendar(projects, nights)
    calendar.sort(key=lambda x: x["date"])

    remaining_by_project = {}

    for name in projects:
        remaining_by_project[name] = project_remaining_hours(name)

    for item in calendar:
        name = item["project"]
        remaining_by_project[name] -= item["hours"]
        item["remaining_after"] = max(0, remaining_by_project[name])

    if not calendar:
        return

    print("\n===== CALENDRIER ASTRO =====\n")

    for item in calendar:
        print(
            f"{item['date']}  "
            f"{item['project']:10}  "
            f"{item['hours']:.1f} h  "
            f"reste après : {item['remaining_after']:.1f} h"
        )

def apply_virtual_session(project, hours):
    target = project.get("target_hours", 0)
    current_hours = project.get("hours", 0)

    project["hours"] = min(
        target,
        current_hours + hours,
    )

    project["remaining"] = max(
        0,
        target - project["hours"],
    )

    project["progress"] = (
        round(
            project["hours"] / target * 100,
            1,
        )
        if target > 0
        else 0
    )

    project["completed"] = project["remaining"] <= 0

    return project

def simulate_portfolio_calendar(nights):

    projects = copy.deepcopy(get_projects())
    completion_dates = {}

    remaining_by_name = {
    name: project_remaining_hours(name)
    for name in projects
    }

    for night in nights:
        
        recommendations = recommend_project_for_night(
        night["top_objects"] + [
        {"name": name, "catalog_key": name, "score": 0}

                for name in projects.keys()],
            available_hours=night.get("duration", 3.0))
        
        if not recommendations:
            continue

        best_project = None
        best_score = -9999

        for p in recommendations[:3]:

            name = p["name"]
            remaining = remaining_by_name.get(name, 0)

            if remaining <= 0:
                continue

            score = p["final_score"]

            if score > best_score:
                best_score = score
                best_project = p

        if not best_project:
            continue

        name = best_project["name"]
        remaining = remaining_by_name[name]

        window = night.get("best_window")

        if window:
            start = int(window["start"].split(":")[0])
            end = int(window["end"].split(":")[0])
            available_hours = max(0, end - start)
        else:
            available_hours = 0

        session_hours = min(available_hours,remaining)

        if session_hours <=0:
            continue

        apply_virtual_session(
            projects[name],
            session_hours)
        
        remaining_by_name[name] = projects[name]["remaining"]
        
        if projects[name].get("completed") and name not in completion_dates:
            completion_dates[name] = night["date"]
            print(f"✓ Projet terminé : {name}")

    return {
    "completion_dates": completion_dates,
    "portfolio_end": None,
    "unfinished_projects": [],
    "remaining_hours": {},
    "unfinished_hours": 0,
    "extra_nights": 0,
    "avg_night_hours": nights,
}

def verdict(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Très bon"
    if score >= 60:
        return "Correct"
    if score >= 40:
        return "Risqué"
    return "Mauvais"


def parse_hourly_weather(data: dict) -> list[dict]:
    if data is None:
        return []
    hourly = data["hourly"]
    rows = []
    
    for i, t in enumerate(hourly["time"]):
        rows.append({
            "time": datetime.fromisoformat(t).replace(tzinfo=ZoneInfo(TIMEZONE)),
            "cloud_cover": hourly["cloud_cover"][i],
            "cloud_cover_low": hourly["cloud_cover_low"][i],
            "cloud_cover_mid": hourly["cloud_cover_mid"][i],
            "cloud_cover_high": hourly["cloud_cover_high"][i],
            "precipitation": hourly["precipitation"][i],
            "relative_humidity_2m": hourly["relative_humidity_2m"][i],
            "visibility": hourly["visibility"][i],
            "wind_speed_10m": hourly["wind_speed_10m"][i],
            "temperature_2m": hourly["temperature_2m"][i],
        })

    return rows

def night_hours_rough(rows: list[dict], date: datetime, lat: float, lon: float, name: str) -> list[dict]:
    tz = ZoneInfo(TIMEZONE)

    city = LocationInfo(
        name,
        "Switzerland",
        TIMEZONE,
        lat,
        lon
    )

    s = sun(
        city.observer,
        date=date.date(),
        tzinfo=tz
    )

    s_next = sun(
        city.observer,
        date=(date + timedelta(days=1)).date(),
        tzinfo=tz
    )

    start = s["dusk"]
    end = s_next["dawn"]

    night_rows = [r for r in rows if start <= r["time"] <= end]

    return night_rows

def compare_equipment_for_object(object_name):
    obj = CATALOG.get(object_name)

    if not obj:
        print(f"Objet inconnu : {object_name}")
        return

    profile = load_user_profile()

    _, _, ranking = select_best_setup_for_object(
        obj_name=object_name,
        profile=profile,
    )

    print(f"\nComparaison matériel pour {object_name}\n")
    print(f"Objet : {obj['name']}")
    print(f"Taille : {obj.get('size_arcmin', '?')} arcmin")

    object_size = obj.get("size_arcmin")

    for item in ranking:
        setup_name = item["setup"]
        setup = EQUIPMENT_PROFILES[setup_name]

        focal = setup["focal_length_mm"]
        sensor_width = setup["sensor_width_mm"]

        fov_width_deg = 57.3 * sensor_width / focal

        fill_ratio = (
            object_size / (fov_width_deg * 60)
            if object_size
            else None
        )

        reasons = item.get("reasons", [])
        reason_text = (
            " • ".join(reasons)
            if reasons
            else "Aucune raison particulière"
        )

        fill_text = (
            f"{fill_ratio:.2f}"
            if fill_ratio is not None
            else "?"
        )

        print(
            f"{setup_name:15s} "
            f"score={item['score']:3} "
            f"sampling={item['arcsec_pixel']}\"/px "
            f"FOV={fov_width_deg:.2f}° "
            f"fill={fill_text}"
        )
        print(f"  {reason_text}")

def imaging_score(obj):
    """
    Score 0-100 basé sur la facilité d'imagerie.
    """

    difficulty = obj.get("imaging_difficulty", 3)
    surface = obj.get("surface_brightness", 3)

    diff_score = 100 - ((difficulty - 1) * 20)
    surf_score = surface * 20

    return round(
        0.6 * diff_score +
        0.4 * surf_score
    )

def recommended_exposure(obj, bortle=4, filter_type=None):
    """
    Retourne le temps de pose recommandé en heures.
    """

    difficulty = obj.get("imaging_difficulty", 3)

    base_hours = {
        1: 2,
        2: 4,
        3: 6,
        4: 10,
        5: 15,
    }

    bortle_factor = {
        1: 0.7,
        2: 0.8,
        3: 0.9,
        4: 1.0,
        5: 1.2,
        6: 1.5,
        7: 2.0,
        8: 3.0,
    }

    hours = (
        base_hours.get(difficulty, 6)
        * bortle_factor.get(bortle, 1.0)
    )
    filter_factor = {
        "LRGB": 1.0,
        "Ha": 1.5,
        "OIII": 2.0,
        "SII": 2.5,
    }

    if filter_type:
        hours *=filter_factor.get(filter_type, 1.0)
    return round(hours, 1)

def load_user_filters():
    try:
        with open("user_filters.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("filters", [])
    except Exception as e:
        print(f"Erreur chargement filtres : {e}")
        return []
    
def recommend_filter(obj):
    filters = load_user_filters()

    obj_type = obj.get("type", "").lower()

    if obj_type == "emission_nebula":
        return [
            f.get("name")
            for f in filters
            if f.get("type") in ["Ha", "OIII", "SII"]
        ]

    elif obj_type == "supernova_remnant":
        return [
            f.get("name")
            for f in filters
            if f.get("type") in ["OIII", "Ha", "SII"]
        ]

    elif obj_type in ["galaxy", "cluster"]:
        return [
            f.get("name")
            for f in filters
            if f.get("type") == "LRGB"
        ]

    return []

def compute_best_window_for_object(
    sky,
    hours,
    illumination,
    moon_rise,
    moon_set,
    city_info,
    lat,
    lon,
    bortle,
    target,
    obj_name,
):
    top_windows = sky.best_windows(
        hours=hours,
        moon_illumination=illumination,
        moon_rise=moon_rise,
        moon_set=moon_set,
        observer=city_info.observer,
        lat=lat,
        lon=lon,
        bortle=bortle,
        target=target,
        target_object=obj_name,
        target_obj=TARGET_OBJECTS[obj_name],
    )

    if not top_windows:
        return None

    top_windows.sort(key=lambda x: x["score"], reverse=True)
    return top_windows[0]


def select_best_setup_for_object(
    obj_name,
    profile,
):
    best_setup = None
    best_setup_score = -999
    setup_ranking = []

    for setup_name in profile.get("available_equipment", []):
        setup = EQUIPMENT_PROFILES.get(setup_name)

        if not setup:
            continue

        setup_result = setup_score(
            setup,
            {
                "name": obj_name,
                "type": CATALOG.get(obj_name, {}).get("type", ""),
            },
        )

        pixel_um = (
            setup.get("pixel_size_um")
            or setup.get("pixel_size_mm")
        )

        arcsec_pixel = (
            round(
                206.265
                * pixel_um
                / setup.get("focal_length_mm"),
                2,
            )
            if setup.get("focal_length_mm") and pixel_um
            else None
        )

        score = setup_result["score"]

        setup_ranking.append(
            {
                "setup": setup_name,
                "score": score,
                "reasons": setup_result["reasons"],
                "arcsec_pixel": arcsec_pixel,
            }
        )

        if score > best_setup_score:
            best_setup_score = score
            best_setup = setup_name

    setup_ranking.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return (
        best_setup,
        best_setup_score,
        setup_ranking,
    )

def build_decision_context(
    *,
    obj_name,
    best,
    selected_setup_profile,
    profile,
    illumination,
    lat,
    lon,
):
    clouds = best.get("clouds", 0)

    camera = Camera(
        manufacturer=selected_setup_profile["camera_manufacturer"],
        model=selected_setup_profile["camera_model"],
        pixel_size_um=selected_setup_profile["pixel_size_um"],
        sensor_width_px=selected_setup_profile["sensor_width_px"],
        sensor_height_px=selected_setup_profile["sensor_height_px"],
        monochrome=selected_setup_profile["monochrome"],
    )

    optics = ImagingOptics(
        manufacturer=selected_setup_profile["optics_manufacturer"],
        model=selected_setup_profile["optics_model"],
        focal_length_mm=selected_setup_profile["focal_length_mm"],
        aperture_mm=selected_setup_profile["aperture_mm"],
        focal_ratio=selected_setup_profile["f_ratio"],
    )

    mount = Mount(
        manufacturer="ZWO",
        model="AM3",
    )

    imaging_filter = ImagingFilter(
        manufacturer="Baader",
        name="H-alpha 6.5nm",
        filter_type="narrowband",
        bandwidth_nm=6.5,
        central_wavelength_nm=656.3,
    )

    setup = ImagingSetup(
        mount=mount,
        optics=optics,
        camera=camera,
        filter=imaging_filter,
    )

    target = CelestialObject(
        name=obj_name,
        object_type=CATALOG.get(obj_name, {}).get("type"),
        angular_size_arcmin=CATALOG.get(obj_name, {}).get("size_arcmin"),
    )

    session_context = SessionContext(
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=3),
        available_duration=timedelta(hours=3),
    )

    site_context = SiteContext(
        name="Buttes",
        latitude=lat,
        longitude=lon,
        elevation=0,
        bortle=profile.get("preferences", {}).get("bortle", 4),
        sqm=best.get("sqm"),
    )

    weather_context = WeatherContext(
        cloud_cover=clouds,
        humidity=best.get("humidity", 0),
        wind_speed_kmh=best.get("wind", 0),
        seeing_arcsec=best.get("seeing"),
        transparency=None,
        temperature_c=None,
        forecast_confidence=None,
        visibility=best.get(
            "visibility",
            best.get("visibility_m", 0),
        ),
    )

    sky_context = SkyContext(
        target=target,
        moon_illumination=illumination,
        moon_separation_deg=best.get("moon_sep", 180),
        target_altitude_deg=best.get("target_altitude"),
        astronomical_darkness=True,
    )

    equipment_context = EquipmentContext(
        setup=setup,
    )

    portfolio_context = PortfolioContext(
        active_projects=0,
        total_remaining_hours=0,
        highest_priority=0,
        average_progress=0,
    )

    preferences_context = PreferencesContext(
        astro_weight=profile.get("preferences", {}).get(
            "astro_weight",
            0.7,
        ),
        project_weight=profile.get("preferences", {}).get(
            "project_weight",
            0.3,
        ),
        minimum_altitude_deg=profile.get("preferences", {}).get(
            "minimum_altitude_deg",
            30,
        ),
        minimum_sqm=profile.get("preferences", {}).get(
            "min_sqm",
            20,
        ),
    )

    return DecisionContext(
        session=session_context,
        site=site_context,
        equipment=equipment_context,
        weather=weather_context,
        sky=sky_context,
        portfolio=portfolio_context,
        preferences=preferences_context,
    )


def build_decision_engine():
    engine = DecisionEngine()

    engine.add_rule(AltitudeRule())
    engine.add_rule(MoonRule())
    engine.add_rule(CloudRule())
    engine.add_rule(HumidityRule())
    engine.add_rule(WindRule())
    engine.add_rule(VisibilityRule())
    engine.add_rule(SeeingRule())
    engine.add_rule(SamplingRule())
    engine.add_rule(ResolutionRule())
    engine.add_rule(ImageQualityRule())
    engine.add_rule(ObjectFitRule())

    return engine


def build_selected_window_weather(
    *,
    hours,
    best,
    sky,
):
    selected_hours = [
        h for h in hours
        if best["start"] <= h["time"] < best["end"]
    ]

    return WeatherForecast(
        hourly=selected_hours,
        hourly_clouds=[
            h.get("cloud_cover", 100)
            for h in selected_hours
        ],
        hourly_humidity=[
            h.get("relative_humidity_2m", 100)
            for h in selected_hours
        ],
        hourly_wind=[
            h.get("wind_speed_10m", 0)
            for h in selected_hours
        ],
        hourly_seeing=[
            sky.estimate_seeing(
                h.get("wind_speed_10m", 0),
                h.get("relative_humidity_2m", 0),
            )
            for h in selected_hours
        ],
        hourly_moon_penalty=[
            detail["moon"]
            for detail in best.get("details", [])
        ],
        hourly_temperature=[
            h.get("temperature_2m", 0)
            for h in selected_hours
        ],
        hourly_visibility=[
            h.get("visibility", 10000)
            for h in selected_hours
        ],
    )


def build_object_evaluation_result(
    *,
    obj_name,
    best,
    best_setup,
    best_setup_score,
    setup_ranking,
    progress,
    remaining_hours,
    roi,
    priority,
    summary,
    decision_context,
    weather,
    hours,
    sky,
):
    return {
        "name": obj_name,
        "score": best["score"],
        "altitude": best.get("target_altitude"),
        "moon_sep": best.get("moon_sep"),
        "sqm": best.get("sqm"),
        "moon_score": best.get("moon_score"),
        "frame_bonus": best.get("frame_bonus"),
        "window": best,
        "catalog_key": obj_name,
        "best_setup": best_setup,
        "setup_score": best_setup_score,
        "global_score": best["score"] + best_setup_score,
        "setup_ranking": setup_ranking,
        "setup_reasons": best["setup_reasons"],
        "arcsec_pixel": best.get("arcsec_pixel"),
        "progress": progress,
        "remaining_hours": remaining_hours,
        "roi": roi,
        "priority": priority,
        "season_bonus": best.get("season_bonus", 0),
        "weather_bonus": best.get("weather_bonus", 0),
        "decision_summary": summary,
        "decision_context": decision_context,
        "weather_context": weather,
        "selected_window_weather": build_selected_window_weather(
            hours=hours,
            best=best,
            sky=sky,
        ),
    }


def evaluate_object(
    obj_name,
    sky,
    hours,
    illumination,
    moon_rise,
    moon_set,
    city_info,
    lat,
    lon,
    bortle,
    target,
    profile,
    weather=None,
):
    best = compute_best_window_for_object(
        sky,
        hours,
        illumination,
        moon_rise,
        moon_set,
        city_info,
        lat,
        lon,
        bortle,
        target,
        obj_name,
    )

    if best is None:
        return None

    best_setup, best_setup_score, setup_ranking = (
        select_best_setup_for_object(
            obj_name=obj_name,
            profile=profile,
        )
    )
    best["best_setup"] = best_setup
    best["setup_score"] = best_setup_score
    best["global_score"] = best["score"] + best_setup_score

    best["setup_reasons"] = setup_ranking[0].get("reasons", []) if setup_ranking else []

    best["arcsec_pixel"] = setup_ranking[0].get("arcsec_pixel") if setup_ranking else None

    selected_setup_profile = (
        EQUIPMENT_PROFILES.get(best_setup)
        if best_setup is not None
        else None
    )

    if selected_setup_profile is None:
        return None

    progress = project_progress(obj_name)
    remaining_hours = project_remaining_hours(obj_name)
    roi = project_roi(obj_name)

    decision_engine = build_decision_engine()

    decision_context = build_decision_context(
        obj_name=obj_name,
        best=best,
        selected_setup_profile=selected_setup_profile,
        profile=profile,
        illumination=illumination,
        lat=lat,
        lon=lon,
    )

    contributions, _ = decision_engine.evaluate(
        decision_context,
        profile,
    )

    from decision.engines.decision_summary_engine import DecisionSummaryEngine

    summary = DecisionSummaryEngine.build(contributions)

    priority = profile.get("project_priorities", {}).get(obj_name, 0)
    
    return build_object_evaluation_result(
        obj_name=obj_name,
        best=best,
        best_setup=best_setup,
        best_setup_score=best_setup_score,
        setup_ranking=setup_ranking,
        progress=progress,
        remaining_hours=remaining_hours,
        roi=roi,
        priority=priority,
        summary=summary,
        decision_context=decision_context,
        weather=weather,
        hours=hours,
        sky=sky,
    )

def build_forecast_result(
    *,
    night_date,
    night_evaluation,
    night_context,
    bortle,
):
    night_score = night_evaluation.night_score
    best = night_evaluation.best
    best_score = night_evaluation.best_score
    best_object = night_evaluation.best_object
    top3 = night_evaluation.top3
    all_results = night_evaluation.all_results
    top_objects_for_night = (
        night_evaluation.top_objects_for_night
    )
    setup_name = night_evaluation.setup_name

    illumination = night_context["illumination"]
    moon_rise = night_context["moon_rise"]
    moon_set = night_context["moon_set"]
    hours = night_context["hours"]
    return {
        "date": str(night_date),
        "score": night_score,
        "moon_impact": best["moon_impact"],
        "moon_penalty": best["moon_penalty"],
        "verdict": verdict(night_score),
        "bortle": bortle,
        "object": best_object,
        "best_setup": setup_name,
        "setup_score": top3[0].get("setup_score", 0),
        "global_score": top3[0].get("global_score", 0),
        "best_object_score": all_results[0]["global_score"],
        "all_objects": all_results,
        "object_evaluations": {
            r["catalog_key"]: r
            for r in top_objects_for_night
        },
        "best_objects": [
            r["name"]
            for r in top3
            if r["score"] == best_score
        ],
        "top_objects": [
            {
                "name": r["name"],
                "score": int(r["score"]),
                "catalog_key": r["catalog_key"],
                "altitude": round(
                    float(r["window"]["target_altitude"]),
                    1,
                ),
                "moon_sep": round(
                    float(r["window"]["moon_sep"]),
                    1,
                ),
                "sqm": round(
                    float(r["window"]["sqm"]),
                    2,
                ),
                "moon_score": round(
                    float(r["window"]["details"][0]["moon"]),
                    1,
                ),
                "frame_bonus": round(
                    float(
                        r["window"]["details"][0]["frame_bonus"]
                    ),
                    1,
                ),
                "project_bonus": round(
                    float(
                        r["window"]["details"][0].get(
                            "project_bonus",
                            0,
                        )
                    ),
                    1,
                ),
                "remaining_hours": project_remaining_hours(
                    r["catalog_key"]
                ),
                "priority_bonus": round(
                    float(
                        r["window"]["details"][0].get(
                            "priority_bonus",
                            0,
                        )
                    )
                ),
                "best_setup": r.get("best_setup"),
                "setup_score": r.get("setup_score", 0),
                "arcsec_pixel": r.get("arcsec_pixel"),
                "global_score": r.get(
                    "global_score",
                    r["score"],
                ),
                "decision_summary": r.get("decision_summary"),
                "decision_context": r.get("decision_context"),
                "weather_context": r.get("weather_context"),
            }
            for r in top_objects_for_night
        ],
        "best_window": {
            "start": best["start"].strftime("%H:%M"),
            "end": best["end"].strftime("%H:%M"),
            "score": best["score"],
        },
        "top_windows": [
            {
                "start": w["start"].strftime("%H:%M"),
                "end": w["end"].strftime("%H:%M"),
                "score": w["score"],
                "sqm": w["sqm"],
                "moon_elevation": w["moon_elevation"],
                "moon_sep": w["moon_sep"],
                "target_altitude": w["target_altitude"],
            }
            for w in all_results[0]["window"].get(
                "top_windows",
                [best],
            )
        ],
        "moon": {
            "illumination": illumination,
            "rise": (
                moon_rise.strftime("%H:%M")
                if moon_rise
                else None
            ),
            "set": (
                moon_set.strftime("%H:%M")
                if moon_set
                else None
            ),
        },
        "weather_summary": {
            "cloud_cover_percent": round(
                sum(h["cloud_cover"] for h in hours)
                / len(hours)
            ),
            "humidity_percent": round(
                sum(h["relative_humidity_2m"] for h in hours)
                / len(hours)
            ),
            "wind_kmh": round(
                sum(h["wind_speed_10m"] for h in hours)
                / len(hours),
                1,
            ),
        },
    }


def forecast_astro(
    lat,
    lon,
    city,
    bortle,
    target="deep_sky",
    equipment=None,
    goal="nebulae",
    weather=None,
):
    if equipment is None:
        equipment = equipment or get_active_equipment()

    rows = forecast_engine.prepare_weather(
    lat,
    lon,
    weather,
)

    if rows is None:
        return []

    results = []

    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    profile = load_user_profile()

    for d in range(7):
        night_date = today + timedelta(days=d)

        night_context = forecast_engine.forecast_one_night(
            night_date=night_date,
            rows=rows,
            lat=lat,
            lon=lon,
            city=city,
            bortle=bortle,
            target=target,
            profile=profile,
        )

        if night_context is None:
            continue

        night_evaluation = portfolio_engine.enrich(
            night_evaluation=night_context["evaluation"],
        )

        results.append(
            build_forecast_result(
                night_date=night_date,
                night_evaluation=night_evaluation,
                night_context=night_context,
                bortle=bortle,
            )
        )

    return results


def best_equipment_for_object(object_name):
    if object_name not in CATALOG:
        return None

    best_setup, best_setup_score, _ = (
        select_best_setup_for_object(
            obj_name=object_name,
            profile=load_user_profile(),
        )
    )

    if best_setup is None:
        return None

    return {
        "equipment": best_setup,
        "score": best_setup_score,
    }

future_engine = FutureOpportunityEngine(
    catalog=CATALOG,
    weather_provider=fetch_weather,
    season_engine=season_days_remaining,
    profile_provider=load_user_profile,
    project_provider=project_remaining_hours,
)
portfolio_forecast_engine = PortfolioForecastEngine(
    future_engine=future_engine,
    score_project=simulated_portfolio_score,
)
tonight_mission_service = TonightMissionService(
    build_mission=NightMissionBuilder.build,
)

forecast_engine = ForecastEngine(
    fetch_weather=fetch_weather,
    parse_hourly_weather=parse_hourly_weather,
    evaluate_object=evaluate_object,
    target_objects=TARGET_OBJECTS,
    moon_phase=moon_phase,
    night_hours_rough=night_hours_rough,
    timezone=TIMEZONE,
    decision_engine_factory=DecisionEngine,
    altitude_rule_factory=AltitudeRule,
)

report_runner = ReportRunner(
    portfolio_forecast_engine=portfolio_forecast_engine,
    show_portfolio_ranking=show_portfolio_ranking,
    show_completion_forecast=show_completion_forecast,
    show_astro_calendar=show_astro_calendar,
    simulate_portfolio_calendar=simulate_portfolio_calendar,
    show_roadmap=show_roadmap,
    show_portfolio_completion_forecast=show_portfolio_completion_forecast,
    present_mission=MissionPresenter.present,
    tonight_mission_service=tonight_mission_service,
)

opportunity_engine = OpportunityEngine()

recommendation_engine = RecommendationEngine()

opportunity_recommendation_service = (
    OpportunityRecommendationService(
        opportunity_engine=opportunity_engine,
        recommendation_engine=recommendation_engine,
    )
)

tonight_runner = TonightRunner(
    report_runner=report_runner,
    portfolio_forecast_engine=portfolio_forecast_engine,
    build_mission_input=build_mission_input,
    recommend_project_for_night=recommend_project_for_night,
    opportunity_recommendation_service=(
        opportunity_recommendation_service
    ),
)

portfolio_engine = PortfolioEngine(
    project_progress=project_progress,
    project_remaining_hours=project_remaining_hours,
    project_priority=project_priority,
    project_roi=project_roi,
    get_projects=get_projects,
)

def main(argv=None) -> int:

    CURRENT_EQUIPMENT = get_active_equipment()
    print("\nSetup actif :", CURRENT_EQUIPMENT)

    parser = argparse.ArgumentParser()
    parser.add_argument(
            "--equipment",
            default=None,
            help="Profil matériel à utiliser"
    )

    parser.add_argument(
        "--compare",
        action="store_true",
        help="Comparer tous les profils matériels"
    )

    parser.add_argument(
        "--goal",
        choices=[
        "balanced",
        "galaxies",
        "nebulae",
        "widefield",
        "small_targets",
        "highest_score",
        "best_setup"
    ],
        default="balanced",
        help="Préférence de sélection des objets"
    )

    parser.add_argument(
        "--mode",
        choices=["tonight", "portfolio", "calendar", "full"],
        default="tonight",
        help="Mode d'affichage"
    )

    parser.add_argument(
        "--object",
        type=str,
        help="Comparer les matériels pour un objet"
    )

    parser.add_argument(
        "--target-object",
        type=str,
        help="Forcer l'analyse complète d'un objet"
    )

    args = parser.parse_args(argv)

    if args.object:
        compare_equipment_for_object(args.object)
        return 0

    if args.target_object:
        obj_key = args.target_object
        obj = CATALOG.get(obj_key)

        if not obj:
            print(f"Objet inconnu : {obj_key}")
            return 0

        print(f"Objet forcé : {obj['name']} ({obj_key})")

        best_setup = best_equipment_for_object(obj_key)

        if best_setup:
            print(
                f"Meilleur setup : "
                f"{best_setup['equipment']} "
                f"(score {best_setup['score']})"
            )

        best_filters = recommend_filter(obj)

        if best_filters:
            print("Filtres conseillés : " + ", ".join(best_filters))

            for filter_name in best_filters:
                filter_type = None

                if "Ha" in filter_name:
                    filter_type = "Ha"
                elif "OIII" in filter_name:
                    filter_type = "OIII"
                elif "SII" in filter_name:
                    filter_type = "SII"
                elif "LRGB" in filter_name:
                    filter_type = "LRGB"

                exposure = recommended_exposure(
                obj,
                    filter_type=filter_type
                )

                print(f"Temps conseillé {filter_name} : {exposure} h")

        else:
            exposure = recommended_exposure(obj)
            print(f"Temps de pose conseillé : {exposure} h")
            print("Filtres conseillés : aucun")

        return 0

    location = get_default_location()
    lat = location["latitude"]
    lon = location["longitude"]
    city = location["name"]

    print(f"\nLieu détecté : {city} ({lat}, {lon})\n")

    weather = fetch_weather(lat, lon)
    
    if weather is None:
        print ("Prévisions météo indisponibles.")
    
    nights = forecast_astro(
        lat,
        lon,
        city,
        bortle=3,
        target=TARGET,
        equipment=args.equipment,
        goal=args.goal,
        weather=weather,
    )

    if nights is None:
        print("ERREUR: forecast_astro a retourné None")
        return 0

    top_nights = sorted(nights, key=lambda x: x["score"], reverse=True)[:3]

    tonight_nights = sorted(
    nights,
    key=lambda night: night["date"],
    )

    night_capacities = forecast_night_capacities(
        lat,
        lon,
        weather=weather,
    )

    print("\n===== CAPACITÉ À VENIR =====")

    total_capacity = sum(c["hours"] for c in night_capacities)

    for c in night_capacities:
        print(f"{c['date']} : {c['hours']:.1f} h qualité={c['quality']:.0f}")

    print(f"Total prévisionnel : {total_capacity:.1f} h")

    if args.mode == "portfolio":
        report_runner.run_portfolio(nights)

    elif args.mode == "calendar":
        report_runner.run_calendar(nights)

    elif args.mode == "tonight":
        if top_nights:
            tonight_runner.run(
                top_nights=tonight_nights,
                night_capacities=night_capacities,
            )

    elif args.mode == "full":
        report_runner.run_full(
            nights=nights,
            night_capacities=night_capacities,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
