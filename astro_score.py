import sys
import math
import json
import requests
import warnings
import copy
from decision.renderer.recommendation_renderer import (
    render_after_tonight_roadmap,
    render_opportunity_cost,
    render_postponement_risk,
    render_strategic_summary,
    render_top_projects,
    render_top_roi,
    render_decision_analysis,)
from decision.portfolio.portfolio_presenter import (show_portfolio_completion_forecast,)
from decision.models.future_opportunity import FutureOpportunity
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
from decision.rules.base_rule import BaseRule
from decision.mission.mission_builder import NightMissionBuilder
from decision.mission.mission_presenter import MissionPresenter
from decision.night_advisor.night_advisor import NightAdvisor
from decision.engines.future_opportunity_engine import FutureOpportunityEngine
from night_scheduler import build_night_schedule
from night_strategy import NightStrategy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from astral import LocationInfo
from astral.sun import sun, dusk ,dawn
from astral.moon import phase as moon_phase, moonrise, moonset
from astral import moon
from astral.sun import sun
from astropy.coordinates import SkyCoord, get_body, EarthLocation, AltAz
from astropy.time import Time
import astropy.units as u
from astropilot.engines.sky_engine import SkyEngine
from astropy.coordinates.baseframe import NonRotationTransformationWarning
from astropilot.catalog import CATALOG
from astropilot.equipment_profiles import CURRENT_EQUIPMENT, get_fov
from astropilot.equipment_profiles import equipment_match_score
from astropilot.equipment_profiles import capture_score
from astropilot.user_profile import (get_default_location, load_user_profile, favorite_targets, get_available_equipment, get_preferences, get_projects, get_decision_weights)
from astropilot.equipment_profiles import (
    get_fov,
    set_current_equipment,
    get_current_equipment,
    list_equipment,
    compare_object_to_equipment
)
import argparse
from astropilot.user_profile import (
    get_default_location,
    load_user_profile,
    favorite_targets,
    get_active_equipment,
    get_available_equipment,
    get_preferences,
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
SEASON_WINDOWS = {
    "M31": {
        "best_months": [8, 9, 10, 11],
        "ok_months": [7, 12],
    },
    "IC1396": {
        "best_months": [6, 7, 8, 9],
        "ok_months": [5, 10],
    },
    "Rosette": {
        "best_months": [12, 1, 2, 3],
        "ok_months": [11, 4],
    },
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

EQUIPMENT_PROFILES = {
    "samyang_183": {
    "name": "Samyang 135 + ASI183MM",
    "focal_length_mm": 135,
    "aperture_mm": 67,
    "sensor_width_mm": 13.2,
    "sensor_height_mm": 8.8,
},

"fra400_2600": {
    "name": "FRA400 + ASI2600MM",
    "focal_length_mm": 400,
    "aperture_mm": 72,
    "sensor_width_mm": 23.5,
    "sensor_height_mm": 15.7,
},

"hyperstar_c8": {
    "name": "Hyperstar C8 + ASI2600MM",
    "focal_length_mm": 390,
    "aperture_mm": 203,
    "sensor_width_mm": 23.5,
    "sensor_height_mm": 15.7,
},
}
CURRENT_EQUIPMENT = get_active_equipment()

print("\nSetup actif :", CURRENT_EQUIPMENT)

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
USE_LEGACY_TONIGHT_REPORT = False

def framing_bonus(target_object):
    obj = CATALOG[target_object]

    fov = get_fov()
    frame_width = fov["width_deg"]
    frame_height = fov["height_deg"]

    object_width = obj.get("width_arcmin", obj.get("size_arcmin", 30)) / 60
    object_height = obj.get("height_arcmin", obj.get("size_arcmin", 30)) / 60

    ratio_w = object_width / frame_width
    ratio_h = object_height / frame_height
    ratio = max(ratio_w, ratio_h)

    
    if 0.3 <= ratio <= 1.0:
        return 10
    elif 0.15 <= ratio < 0.3:
        return 5
    elif 1.0 <= ratio < 1.5:
        return 0
    elif 1.5 < ratio <= 2.0:
        return 0
    elif 2.0 < ratio <= 3.0:
        return -5
    else:
        return -20

def forecast_night_capacities(lat, lon, days=14):

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


def estimate_weather_good_night_ratio(weather):
    if not weather or "hourly" not in weather:
        return 0.35

    hourly = weather["hourly"]
    times = hourly.get("time", [])
    clouds = hourly.get("cloud_cover", [])
    humidity = hourly.get("relative_humidity_2m", [])
    wind = hourly.get("wind_speed_10m", [])
    precipitation = hourly.get("precipitation", [])

    good_hours = 0
    total_night_hours = 0

    for i, t in enumerate(times):
        hour = int(t[11:13])

        if hour < 22 and hour > 4:
            continue

        total_night_hours += 1

        cloud = clouds[i] if i < len(clouds) else 100
        hum = humidity[i] if i < len(humidity) else 100
        wnd = wind[i] if i < len(wind) else 99
        rain = precipitation[i] if i < len(precipitation) else 99

        if cloud <= 40 and hum <= 85 and wnd <= 25 and rain == 0:
            good_hours += 1

    if total_night_hours == 0:
        return 0.35

    return max(0.05, min(0.8, good_hours / total_night_hours))
    
def estimated_sqm(bortle, moon_illumination, moon_elevation, moon_target_sep):
    base = {
        1: 21.9,
        2: 21.7,
        3: 21.3,
        4: 20.8,
        5: 20.2,
        6: 19.5,
        7: 18.8,
        8: 18.2,
        9: 17.5,
    }.get(bortle, 20.0)

    if moon_elevation <= 0:
        moon_loss = 0
    else:
        sep_factor = max(0.3, 1 - moon_target_sep / 180)

        moon_loss = (
        (moon_illumination / 100)**1.4
        * (moon_elevation / 90)
        * sep_factor
        * 2.5
    )

    return round(base - moon_loss, 2)


def season_days_remaining(obj):
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    current_month = today.month

    name = obj.get("catalog_key") or obj.get("name")
    season = SEASON_WINDOWS.get(name)

    if not season:
        return None

    months = season.get("best_months", []) + season.get("ok_months", [])

    if not months:
        return None

    if current_month not in months:
        return 0

    future_months = [m for m in months if m >= current_month]

    if future_months:
        last_month = max(future_months)
    else:
        last_month = max(months)

    year = today.year

    if last_month < current_month:
        year += 1

    if last_month == 12:
        season_end = datetime(year + 1, 1, 1).date()
    else:
        season_end = datetime(year, last_month + 1, 1).date()

    return max(0, (season_end - today).days)



def season_bonus(obj):
    """
    Bonus saisonnier basé sur le mois courant.
    Plus fin que l'ancien système best/ok/hors saison.
    """
    month = datetime.now(ZoneInfo(TIMEZONE)).month

    name = obj.get("catalog_key") or obj.get("name")

    season = SEASON_WINDOWS.get(name)
    if not season:
        return 0

    best_months = season.get("best_months", [])
    ok_months = season.get("ok_months", [])

    if month in best_months:
        return 15

    if month in ok_months:
        return 5

    # Mois adjacent à une fenêtre correcte = faible bonus
    adjacent_months = set()

    for m in best_months + ok_months:
        adjacent_months.add(12 if m == 1 else m - 1)
        adjacent_months.add(1 if m == 12 else m + 1)

    if month in adjacent_months:
        return 0

    return -10


    # Projet terminable cette nuit
    if remaining <= available_hours:
        return 20

    # Projet terminable en environ deux nuits
    if remaining <= available_hours * 2:
        return 10

    return 0


def season_urgency_bonus(obj):
    days = season_days_remaining(obj)

    name = obj.get("catalog_key") or obj.get("name")
    
    if days is None:
        return 0

    if days <= 0:
        return 0

    if days <= 30:
        return 25

    if days <= 60:
        return 15

    if days <= 90:
        return 8

    if days <= 150:
        return 3

    return 0

def season_bonus(obj):
    """
    Bonus saisonnier selon le mois actuel.
    """
    month = datetime.now().month

    name = obj.get("catalog_key", "").upper()

    bonus = 0

    # M31 : août → novembre
    if name == "M31":
        if month in [8, 9, 10, 11]:
            bonus += 25
        elif month in [6, 7]:
            bonus += 10
        elif month in [12, 1]:
            bonus += 5
        else:
            bonus -= 20

    # Rosette : novembre → mars
    elif "ROSETTE" in name:
        if month in [11, 12, 1, 2, 3]:
            bonus += 25
        elif month in [10, 4]:
            bonus += 10
        else:
            bonus -= 20

    # IC1396 : juin → octobre
    elif name == "IC1396":
        if month in [6, 7, 8, 9, 10]:
            bonus += 25
        elif month in [5, 11]:
            bonus += 10
        else:
            bonus -= 20

    return bonus

def estimate_portfolio_nights():
    projects = get_projects()

    total_remaining = 0

    for project in projects.values():
        target = project.get("target_hours", 0)
        done = project.get("hours", 0)

        total_remaining += max(0, target - done)

    HOURS_PER_NIGHT = 4

    return round(total_remaining / HOURS_PER_NIGHT, 1)

def project_remaining_hours(object_name):
    projects = get_projects()

    if object_name not in projects:
        return None

    project = projects[object_name]
    hours = project.get("hours", 0)
    target_hours = project.get("target_hours", 0)

    return max(0, round(target_hours - hours, 1))

def regret_score(project_name):
    future = future_engine.estimate (project_name)

    good_nights = max(1, future.good_nights)
    remaining = project_remaining_hours(project_name)

    if remaining is None or remaining <= 0:
        return 0

    regret = remaining / good_nights

    return round(min(10, regret), 1)

def marginal_gain_factor(progress):
    """
    Pondère la valeur de la prochaine session selon l'avancement du projet.
    Début de projet : chaque heure structure beaucoup le projet.
    Fin de projet : les heures restantes servent surtout à clôturer.
    """

    if progress >= 95:
        return 0.5

    elif progress >= 80:
        return 0.8

    elif progress >= 50:
        return 1.0

    elif progress >= 20:
        return 1.2

    else:
        return 1.4


def project_progress(object_name):
    projects = get_projects()

    if object_name not in projects:
        return 0

    project = projects[object_name]

    hours_done = project.get("hours", 0)
    target_hours = project.get("target_hours", 1)

    if target_hours <= 0:
        return 0

    return round((hours_done / target_hours) * 100, 1)

def portfolio_gain_if_shot(object_name, session_hours=3.0):
    projects = get_projects()

    if object_name not in projects:
        return 0

    before = project_progress(object_name)
    marginal_factor = marginal_gain_factor(before)

    project = projects[object_name]

    current_hours = project.get("hours", 0)
    target_hours = project.get("target_hours", 1)

    simulated_hours = min(
        current_hours + session_hours,
        target_hours
    )

    after = round(
        simulated_hours / target_hours * 100,
        1
    )

    gain = after - before

    gain *= marginal_factor

    return round(gain, 1)


def estimate_remaining_nights(hours_remaining, nights=None):
    if hours_remaining is None:
        return 0

    if isinstance(hours_remaining, str):
        hours_remaining = project_remaining_hours(hours_remaining)

    if hours_remaining is None:
        return 0

    avg_capacity = average_night_capacity(nights) if nights else 3.0

    return hours_remaining / max(1, avg_capacity)

def evaluate_project_session(project, session_hours):
    remaining_before = project_remaining_hours(project["catalog_key"])

    actual_hours = min(session_hours, remaining_before)

    gain = (
        actual_hours / project["planned_hours"]
    ) * 100

    remaining_after = max(
        0,
        remaining_before - actual_hours
    )

    completed = remaining_after <= 0

    roi = 0
    if actual_hours > 0:
        roi = gain / actual_hours

    return {
        "project": project["catalog_key"],
        "hours": actual_hours,
        "gain": gain,
        "roi": roi,
        "remaining_after": remaining_after,
        "completed": completed,
    }


def portfolio_completion_roadmap():
    projects = get_projects()

    roadmap = []

    for name, project in projects.items():

        remaining = max(
            0,
            project["target_hours"] - project["hours"]
        )

        if remaining <= 0:
            continue

        roadmap.append({
            "name": name,
            "remaining": remaining,
            "score": portfolio_score(name)
        })

    roadmap.sort(
        key=lambda p: p["score"],
        reverse=True
    )

    return roadmap

def show_portfolio_completion_roadmap():

    roadmap = portfolio_completion_roadmap()

    print("\n===== ROADMAP PORTEFEUILLE =====")

    for idx, project in enumerate(roadmap, start=1):

        nights = estimate_remaining_nights(
            project["name"]
        )

        print(
            f"\n{idx}. {project['name']}"
        )

        print(
            f"   score : {project['score']:.1f}"
        )

        print(
            f"   reste : {project['remaining']:.1f} h"
        )

        print(
            f"   nuits : {nights}"
        )

    print("\n===== FIN DU PORTEFEUILLE =====")

    total_hours = sum(
        p["remaining"]
        for p in roadmap
    )

    print(
        f"Temps restant total : "
        f"{total_hours:.1f} h"
    )

    print(
        f"Nuits estimées : "
        f"{estimate_portfolio_nights()}"
    )

def simulate_multi_night_portfolio_roadmap(avg_night_hours=5):
    roadmap = portfolio_completion_roadmap()

    simulated = []

    current_night = 1

    for project in roadmap:

        remaining = project["remaining"]

        while remaining > 0:

            hours_this_night = min(
                avg_night_hours,
                remaining
            )

            simulated.append({
                "night": current_night,
                "project": project["name"],
                "hours": hours_this_night,
                "remaining_after": max(
                    0,
                    remaining - hours_this_night
                ),
                "completed":
                    remaining - hours_this_night <= 0
            })

            remaining -= hours_this_night
            current_night += 1

    return simulated

def simulated_portfolio_score(project):

    remaining = (
        project["target_hours"]
        - project["hours"]
    )

    progress = (
        project["hours"]
        / project["target_hours"]
        * 100
    )

    importance = project.get(
        "importance",
        5
    )

    closure_bonus = 0

    if remaining > 0:
        closure_bonus = min(
        40,
        round(120 / remaining, 1)
    )

    return (
        importance * 10
        + progress * 0.5
        + closure_bonus
    )



def simulate_dynamic_portfolio_roadmap(night_capacities=None, avg_night_hours=5):
    projects = copy.deepcopy(get_projects())

    simulated = []
    current_night = 1

    while True:
        if night_capacities and current_night > len(night_capacities):
            break

        if current_night > 50:
            print("STOP sécurité roadmap dynamique")
            break

        active_projects = {}

        for name, project in projects.items():
            remaining = project["target_hours"] - project["hours"]

            if remaining > 0:
                active_projects[name] = project

        if not active_projects:
            break

        best_name = None
        best_score = -9999

        for name, project in active_projects.items():

            future = future_engine.estimate (name)
            base_score =simulated_portfolio_score(project)

            ratio = future.opportunity_ratio

            opportunity_bonus = max(
                0,
                min(30, round(30 / max(ratio, 0.1), 1))
            )


            score = base_score + opportunity_bonus

            if score > best_score:
                best_score = score
                best_name = name

        project = projects[best_name]

        remaining = (
            project["target_hours"]
            - project["hours"]
        )

        if night_capacities:
            capacity = night_capacities[current_night - 1]
            hours_available = capacity.get("hours", avg_night_hours)
        else:
            capacity = None
            hours_available = avg_night_hours

        hours_this_night = min(
            hours_available,
            remaining
        )

        if hours_this_night <= 0:
            current_night += 1
            continue

        project["hours"] += hours_this_night

        simulated.append({
            "night": current_night,
            "date": capacity.get("date") if capacity else None,
            "capacity": hours_available,
            "project": best_name,
            "score": best_score,
            "hours": hours_this_night,
            "remaining_after": max(
                0,
                remaining - hours_this_night
            ),
            "completed": remaining - hours_this_night <= 0
        })

        current_night += 1

    return simulated


def show_multi_night_portfolio_roadmap(night_capacities=None, avg_night_hours=5):

    simulated = simulate_dynamic_portfolio_roadmap(
        night_capacities=night_capacities,avg_night_hours = avg_night_hours
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


def project_priority(object_name):
    projects = get_projects()

    if object_name not in projects:
        return 0

    project = projects[object_name]
    importance = project.get("importance", 5)

    hours = project.get("hours", 0)
    target = project.get("target_hours", 0)

    if target <= 0:
        return 0

    completion = hours / target
    remaining = max(0, target - hours)

    if completion < 0.20:
        completion_bonus = 0
    elif completion < 0.50:
        completion_bonus = 3
    elif completion < 0.75:
        completion_bonus = 7
    elif completion < 0.90:
        completion_bonus = 12
    else:
        completion_bonus = 20

    start_bonus = 0
    remaining_pressure = min(remaining, 20)

    base_priority = start_bonus + completion_bonus + remaining_pressure

    return round(base_priority * (importance / 5), 1)

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

def urgency_bonus(obj):

    altitude = obj.get("altitude", 0)

    if altitude < 25:
        return 20

    elif altitude < 35:
        return 10

    return 0

def season_remaining_months(obj):
    ra = obj.get("ra_hours")

    if ra is None:
        return 6

    current_month = datetime.now().month

    optimal_month = int((ra / 2) % 12) + 1

    diff = (optimal_month - current_month) % 12

    return max(1, 12 - diff)


def season_window_bonus(obj):
    months = season_remaining_months(obj)

    if months <= 1:
        return 30

    if months <= 2:
        return 20

    if months <= 4:
        return 10

    return 0


def project_details(object_name):
    projects = get_projects()

    if object_name not in projects:
        return None

    project = projects[object_name]

    hours = project.get("hours", 0)
    target = project.get("target_hours", 0)
    importance = project.get("importance", 5)

    remaining = max(0, target - hours)

    progress = 0
    if target > 0:
        progress = round(hours / target * 100, 1)

    return {
        "importance": importance,
        "progress": progress,
        "remaining": remaining,
        "remaining_nights": estimate_remaining_nights(object_name)
    }
def risk_label_to_score(risk):
    mapping = {
        "FAIBLE": 20,
        "MOYEN": 50,
        "ÉLEVÉ": 80,
        "CRITIQUE": 100,
    }

    return mapping.get(str(risk).upper(), 50)

def compute_postponement_risk_score(future, days_left):
    """
    Calcule un risque de report continu (0-100)
    basé sur les opportunités futures réelles.
    """

    good_nights = future.good_nights
    opportunity_ratio = future.opportunity_ratio

    # Peu de bonnes nuits => risque élevé
    window_risk = max(0, 100 - good_nights * 4)

    # Fin de saison proche => risque élevé
    season_risk = max(0, 100 - days_left)

    # Ratio d'opportunité élevé => risque élevé
    ratio_risk = min(100, opportunity_ratio * 10)

    risk = (
        window_risk * 0.5
        + season_risk * 0.3
        + ratio_risk * 0.2
    )

    return round(max(0, min(risk, 100)), 1)

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

def project_roi(object_name):
    details = project_details(object_name)

    if not details:
        return 0

    remaining = details["remaining"]

    if remaining <= 0:
        return 0

    importance = details["importance"]
    progress = details["progress"]

    completion_multiplier = 1 + progress / 100

    roi = importance * completion_multiplier / remaining

    return round(roi, 2)


def framing_score(setup, project_name):

    object_size = OBJECT_SIZES.get(project_name)

    if not object_size:
        return 0

    focal = setup.get("focal_length", 135)
    sensor_width = setup.get("sensor_width", 23.5)

    fov_width_deg = 57.3 * sensor_width / focal
    fov_width_arcmin = fov_width_deg * 60

    fill_ratio = object_size / fov_width_arcmin

    ######print(
    #####project_name,
    ####"size=", object_size,
    ###"fov=", round(fov_width_arcmin, 1),
    ##"fill=", round(fill_ratio, 2)
    #)

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

def explain_setup_choice(setup, obj):
    reasons = []

    obj_type = obj.get("type", "")

    if setup.get("f_ratio", 99) <= 2.8:
        reasons.append("Optique très lumineuse")

    if setup.get("camera", "").lower().endswith("2600"):
        reasons.append("Capteur haute résolution")

    if setup.get("camera", "").lower().endswith("183"):
        reasons.append("Très bon échantillonnage")

    if obj_type == "galaxy":
        reasons.append("Adapté aux objets compacts")

    if obj_type == "nebula":
        reasons.append("Champ adapté aux nébuleuses")

    return reasons

def session_portfolio_gain(project_name, session_hours):

    project = get_projects().get(project_name, {})

    target = project.get("target_hours", 0)

    if target <= 0:
        return 0

    current_hours = project.get("hours", 0)

    current_progress = (current_hours / target) * 100

    future_hours = min(
        current_hours + session_hours,
        target
    )

    future_progress = (future_hours / target) * 100

    return round(
        future_progress - current_progress,
        1
    )
def save_user_profile(profile):
    with open("data/user_profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=4, ensure_ascii=False)

def log_project_session(object_name, session_hours):
    profile = load_user_profile()

    projects = profile.get("projects", {})

    if object_name not in projects:
        print(f"Projet {object_name} introuvable")
        return

    current_hours = projects[object_name].get("hours", 0)

    projects[object_name]["hours"] = round(
        current_hours + float(session_hours),
        1
    )
    session = {
    "date": datetime.now().strftime("%Y-%m-%d"),
    "object": object_name,
    "hours": float(session_hours),
    }
    profile.setdefault("sessions", []).append(session)

    save_user_profile(profile)

    remaining = project_remaining_hours(object_name)

    print(f"Projet {object_name} mis à jour")
    print(f"Ancien total : {current_hours} h")
    print(f"Ajout : {session_hours} h")
    print(f"Nouveau total : {projects[object_name]['hours']} h")

    if remaining is not None:
        print(f"Reste : {remaining} h")

def closure_bonus(name, available_hours=3.0):
    remaining = project_remaining_hours(name)

    if remaining is None or remaining <= 0:
        return 0

    # Vrai bonus de clôture uniquement si le projet peut être fini ce soir
    if remaining <= available_hours:
        return 15

    # Petit bonus si le projet est proche de la fin
    if remaining <= available_hours * 2:
        return 6

    if remaining <= available_hours * 3:
        return 3

    return 0

def progression_bonus(name):
    remaining = project_remaining_hours(name)
    project = get_projects().get(name, {})

    target = project.get("target_hours", 0)
    hours = project.get("hours", 0)

    if target <= 0:
        return 0

    progress = hours / target * 100

    if progress <= 0:
        return 12

    if progress < 20:
        return 8

    if progress < 50:
        return 4

    return 0

def diversification_bonus(name):
    """
    Bonus stratégique si la catégorie de l'objet est sous-représentée
    en heures restantes dans le portefeuille.
    """

    obj = CATALOG.get(name, {})
    category = obj.get("type", "").lower()

    if not category:
        return 0

    loads = portfolio_category_load()

    if not loads:
        return 0

    total_load = sum(loads.values())

    if total_load <= 0:
        return 0

    category_load = loads.get(category, 0)
    category_share = category_load / total_load

    # Si la catégorie représente moins de 20 % de la charge restante,
    # elle est fortement sous-représentée.
    if category_share < 0.20:
        return 8

    # Entre 20 % et 35 %, elle est modérément sous-représentée.
    if category_share < 0.35:
        return 4

    return 0


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


def portfolio_category_load():
    """
    Charge restante du portefeuille par catégorie.
    Retourne par exemple :
    {
        "nebula": 37,
        "galaxy": 8,
        "cluster": 3,
    }
    """

    loads = {}

    for name, project in get_projects().items():

        remaining = project_remaining_hours(name)

        if remaining <= 0:
            continue

        obj = CATALOG.get(name, {})

        category = obj.get("type", "").lower()

        if not category:
            continue

        loads[category] = loads.get(category, 0) + remaining

    return loads


def portfolio_roadmap():
    projects = get_projects()

    roadmap = []

    for name, project in projects.items():

        remaining = project_remaining_hours(name)

        if remaining is None or remaining <= 0:
            continue

        roi = project_roi(name)

        roadmap.append({
            "name": name,
            "remaining": remaining,
            "roi": roi,
            "nights": round(remaining / 3, 1)
        })

    roadmap.sort(key=lambda x: x["roi"], reverse=True)

    return roadmap


def recommend_project():
    projects = get_projects()

    candidates = []

    for name, project in projects.items():
        remaining = project_remaining_hours(name)

        if remaining is None or remaining <= 0:
            continue

        obj = CATALOG.get(name,{})

        priority = project_priority(name)
        progress = project_progress(name)

        if progress >= 95:
            completion_bonus = 30
        elif progress >= 85:
            completion_bonus = 20
        elif progress >= 70:
            completion_bonus = 10
        else:
            completion_bonus = 0
        closure = closure_bonus(name)
        season_bonus = urgency_bonus(obj)
        season_window = season_window_bonus(obj)
        urgency = season_urgency_bonus(obj)
        roi = project_roi(name)

        portfolio_score = (
            priority * 0.6
            + season_bonus
            + season_window
            + urgency
            + roi * 15
            + completion_bonus
            + closure
        )
        project_gain = session_portfolio_gain(
           name,
           min(2.0, remaining) 
        )

        candidates.append({
            "name": name,
            "remaining": remaining,
            "priority": priority,
            "project_gain": project_gain,
            "hours_done": project.get("hours", 0),
            "target_hours": project.get("target_hours", 0),
            "season_bonus": season_bonus,
            "roi": roi,
            "portfolio_score": portfolio_score,
            "season_window": season_window,
            "urgency" : urgency,
            "months_left": season_remaining_months(CATALOG.get(name,{})),
            "progress" : progress,
            "comnpletion_bonus": completion_bonus,
            "closure_bonus" : closure
        }),
            


    if not candidates:
        return None
    
    candidates.sort(
        key=lambda x: x["portfolio_score"],
        reverse=True
        )
    print (f"Bonus clotûre : {closure_bonus(name)}")
    print("\n===== TOP GAINS CE SOIR =====\n")

    for i, c in enumerate(candidates[:3], start=1):
        print(
            f"{i}. {c['name']}  "
            f"gain=+{c['project_gain']:.1f}%  "
            f"roi={c['roi']:.2f}  "
            f"reste={c['remaining']:.1f}h"
        )

    return candidates[0]

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
        altitude = urgency_bonus(obj)
        season = season_bonus(obj)
        season_urgency = season_urgency_bonus(obj)
        roi = project_roi(catalog_key)

        future = future_engine.estimate (catalog_key)

        days_left = season_days_remaining(obj)

        risk_label = future.risk

        # Ancien système
        risk_v1 = risk_label_to_score(risk_label)

        # Nouveau système
        risk_v2 = compute_postponement_risk_score(
            future,
            days_left,
        )

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

        future = future_engine.estimate (catalog_key)
        opportunity_ratio = future.opportunity_ratio

        opportunity_bonus = max(
            0,
            min(8, round(8 / max(opportunity_ratio, 0.1), 1))
        )

        regret = regret_score(catalog_key)
        regret_bonus = min(5, regret * 1.2)

        progression = progression_bonus(catalog_key)
        diversity_bonus = diversification_bonus(catalog_key)

        category_loads = portfolio_category_load()

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

        postponement_impact = compute_postponement_impact(
            postponement_risk=postponement_risk,
            confidence=obj.get("confidence", "MOYENNE"),
            project_priority=priority,
            astro_score=astro_score,
        )

        final_score = (
            astro_part
            + altitude
            + season
            + season_urgency
            + portfolio_bonus
        + postponement_impact["postponement_net_impact"]
        )

        strategy_scores = {}

        for mode in ["balanced", "roi", "completion", "diversification", "risk"]:
            weights = strategy_weights(mode)

            strategy_scores[mode] = round(
                astro_part * weights["astro"]
                + roi_bonus * weights["roi"]
                + postponement_impact["postponement_net_impact"] * weights["report"]
                + completion_bonus * weights["completion"]
                + diversity_bonus * weights["diversity"],
                1
            )

        if decision_mode in strategy_scores:
            decision_score = strategy_scores[decision_mode]
        else:
            decision_score = final_score

        # Limite l’avantage portefeuille si l’objet est surtout choisi grâce au portefeuille
        if portfolio_bonus > astro_part * 0.5:
            final_score -= portfolio_bonus * 0.3

        if astro_score <= 0:
            final_score -= 30
            decision_score -= 30

        remaining = project_remaining_hours(catalog_key)

        if remaining is not None and remaining <= available_hours:
            final_score += 30

        candidates.append({
            "name": obj["name"],
            "catalog_key": catalog_key,
            "priority": priority,
            "astro_score": astro_score,
            "final_score": final_score,
            "decision_score": decision_score,
            "season_bonus": season,
            "altitude_bonus": altitude,
            "roi": roi,
            "portfolio_score": portfolio_bonus,
            "global_score": obj.get("global_score", astro_score),
            "setup_score": obj.get("setup_score", 0),
            "best_setup": obj.get("best_setup"),
            "completion_bonus": completion_bonus,
            "closure_bonus": closure,
            "postponement_risk": postponement_risk,
            "postponement_penalty": postponement_impact["postponement_penalty"],
            "urgency_bonus": postponement_impact["urgency_bonus"],
            "postponement_net_impact": postponement_impact["postponement_net_impact"],
            "postponement_reason": postponement_impact["postponement_reason"],
            "reasons": explain_recommendation({
                "astro_score": astro_score,
                "roi": roi,
                "postponement_risk": postponement_risk,
                "completion_bonus": completion_bonus,
                "closure_bonus": closure,
                "season_bonus": season,
                "progression_bonus": progression,
                "diversity_bonus" : diversity_bonus, 
        }),

            "strategy_scores": strategy_scores,
        })

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x["decision_score"],
        reverse=True
    )

    return candidates


def build_night_schedule_legacy_old(top_objects, available_hours):
    """
    Remplit une nuit avec plusieurs projets.
    """

    schedule = []
    remaining = available_hours

    for obj in top_objects:

        project = recommend_project_for_object(
            obj.get("catalog_key", obj.get("name"))
        )

        if not project:
            continue

        needed = min(project["remaining"], remaining)

        if needed <= 0:
            continue

        schedule.append({
            "object": obj["name"],
            "project": project["name"],
            "hours": round(needed, 1),
        })

        remaining -= needed

        if remaining <= 0:
            break

    return schedule

def recommend_project_for_object(object_key):

    projects = get_projects()

    candidates = []

    for name, project in projects.items():

        if name != object_key:
            continue

        remaining = project_remaining_hours(name)

        if remaining <= 0:
            continue

        candidates.append({
            "name": name,
            "remaining": remaining,
        })

    if not candidates:
        return None

    return candidates[0]

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

def next_project_after(current_project):
    projects = get_projects()

    ranking = []

    for name, project in projects.items():

        if name == current_project:
            continue

        remaining = max(
            0,
            project["target_hours"] - project["hours"]
        )

        if remaining <= 0:
            continue

        score = portfolio_score(name)
        
        ranking.append(
            {
                "name": name,
                "score": score,
                "remaining": remaining,
            }
        )

    ranking.sort(
        key=lambda x: x["score"],
        reverse=True
)

    for idx, p in enumerate(ranking, start=1):
        p["rank"] = idx

        if ranking:
            ranking[0]["total_projects"] = len(ranking)
            return ranking[0]

    return None

def show_project_stats():
    profile = load_user_profile()

    projects = profile.get("projects", {})
    sessions = profile.get("sessions", [])

    print("\n===== STATISTIQUES =====\n")

    total_hours = 0

    for name, data in projects.items():
        hours = data.get("hours", 0)
        total_hours += hours

        remaining = max(
            0,
            data.get("target_hours", 0) - hours
        )
        priority = project_priority(name)
        print(
            f"{name:15}"
            f"{hours:5.1f} h   "
            f"reste {remaining:5.1f} h"
            f"prio {priority:5.1f}"
        )
        print()
        print(f"Temps total acquis : {total_hours:.1f} h")
        print(f"Nombre de sessions : {len(sessions)}")

    if projects:
        best = max(
        projects.items(),
        key=lambda x: x[1].get("hours", 0)
    )

        print(
            f"Projet principal : "
            f"{best[0]} ({best[1]['hours']:.1f} h)"
        )

def show_tonight_recommendation(night):

    night_projects = recommend_project_for_night(
        night["top_objects"],
        available_hours=night.get("duration",
                                  3.0)
    )

    if not night_projects:
        print("\nAucun projet actif trouvé")
        return

    session_hours = night.get("duration", 3.0)

    render_top_projects(
        night_projects=night_projects,
        session_hours=session_hours,
        portfolio_gain_if_shot=portfolio_gain_if_shot,
        session_portfolio_gain=session_portfolio_gain,
    )

    render_top_roi(
        night_projects=night_projects,
        session_hours=session_hours,
        portfolio_gain_if_shot=portfolio_gain_if_shot,
    )
    
    best_score = night_projects[0]

    best_roi = max(
        night_projects,
        key=lambda p: portfolio_gain_if_shot(
            p["name"],
            session_hours=session_hours,
        ) / session_hours,
    )

    render_decision_analysis(
        best_score=best_score,
        best_roi=best_roi,
    )
    score_gap = 0.0
    roi_gap = 0.0

    if best_score["name"] != best_roi["name"]:
        score_gap = (
            best_score["final_score"]
            - best_roi["final_score"]
        )

        best_roi_value = (
            portfolio_gain_if_shot(
                best_roi["name"],
                session_hours=session_hours,
            )
            / session_hours
        )

        best_score_roi = (
            portfolio_gain_if_shot(
                best_score["name"],
                session_hours=session_hours,
            )
            / session_hours
        )

        roi_gap = best_roi_value - best_score_roi

    progress = project_progress(best_score["name"])
    remaining = project_remaining_hours(best_score["name"])

    print("\nUrgence portefeuille :")

    print(
        f"✓ Progression actuelle : "
        f"{progress:.1f}%"
    )

    if remaining is not None :
        print(f"✓ Temps restant : {remaining:.1f} h")
    else:
        print(f"✓ Temps restant : inconnu ")

    if best_score.get("closure_bonus", 0) > 0:
        print(
            f"✓ Bonus clôture disponible : "
            f"+{best_score['closure_bonus']:.0f}"
        )

    if best_score["name"] != best_roi["name"]:
        print(f"Pourquoi {best_score['name']} ?")
        print(
        f"✓ Score astro supérieur de {score_gap:.1f} points"
        )

    remaining = project_remaining_hours(best_score["name"])

    if remaining <= session_hours:
        print("✓ Projet terminable cette nuit")
    elif remaining <= 10:
        print(f"✓ Plus que {remaining:.1f} h avant achèvement")

        print("\nAlternative :")
        print(f"→ {best_roi['name']}")

        roi_gap = locals().get("roi_gap", 0)

        print(
            f"✓ ROI supérieur de {roi_gap:.2f}/h"
        )

        print("\n===== SI JE RATE CETTE NUIT =====")

        missed_gain = portfolio_gain_if_shot(
            best_score["name"],
            session_hours=session_hours
        )

        print(f"Projet recommandé : {best_score['name']}")
        print(f"Progression perdue : -{missed_gain:.1f}%")

        if best_score.get("closure_bonus", 0) > 0:
            print("Impact : projet non terminé ce soir")
            print("Impact : bonus clôture perdu")

        print("Décision : cette nuit a une valeur forte" if missed_gain >= 10 else "Décision : impact modéré")

    print("\n===== PLAN MULTI-OBJETS =====")

    schedule = build_night_schedule(
        night["top_objects"],
        2.0
        )

    for item in schedule:
        print(
            f"{item['start']:.1f}h -> {item['end']:.1f}h   "
            f"{item['object']}   "
            f"{item['hours']:.1f} h"
        )

    night_project = night_projects[0]

    obj_key = night_project["name"]
    obj = CATALOG.get(obj_key, {"name": obj_key})

    best_setup = best_equipment_for_object(obj_key)
    best_filters = recommend_filter(obj)

    print(f"Projet : {night_project['name']}")
    print(f"Score astro : {night_project['astro_score']:.1f}")
    print(f"Priorité projet : {night_project['priority']:.1f}")
    print(f"Bonus saison : +{night_project.get('season_bonus',0):.1f}")
    print(f"Fenêtre saison : +{night_project.get('season_window',0):.1f}")
    print(f"Urgence saison : +{night_project.get('urgency',0):.1f}")
    print(f"Bonus progression : +{night_project.get('completion_bonus',0):.1f}")
    print(f"Score final : {night_project['final_score']:.1f}")

    print("\n===== PLAN DE NUIT =====")

    window = night.get("best_window")

    if window:
        print(f"Fenêtre optimale : {window['start']} → {window['end']}")

    remaining_action = project_remaining_hours(night_project["name"])

    if remaining_action is not None and remaining_action <= session_hours:
        action = "terminer"
    else:
        action = "poursuivre"

    print(f"Action recommandée : {action} {night_project['name']}")
    print(f"Bonus saison : +{night_project.get('season_bonus', 0):.1f}")
    print(f"ROI projet : {night_project.get('roi', 0):.2f}")
    print(f"Bonus clôture : +{night_project.get('closure_bonus', 0):.1f}")


    if best_setup:
        print(f"Setup : {best_setup['equipment']}")

    if best_filters:
        print(f"Filtre : {best_filters[0]}")

    show_action_plan(
        night,
        night_project,
        best_setup,
        best_filters,
        night_capacities=night_capacities
    )

    same_choice = (
    best_score["name"].strip().upper()
    == best_roi["name"].strip().upper()
    )
    remaining_best = project_remaining_hours(best_score["name"])
    remaining_roi = project_remaining_hours(best_roi["name"])

    gain_score = portfolio_gain_if_shot(
        best_score["name"],
        session_hours,
        )

    gain_roi = portfolio_gain_if_shot(
        best_roi["name"],
        session_hours,
    )

    render_opportunity_cost(
        best_score=best_score,
        best_roi=best_roi,
        session_hours=session_hours,
        remaining_best=remaining_best,
        remaining_roi=remaining_roi,
        gain_score=gain_score,
        gain_roi=gain_roi,
        same_choice=same_choice,
    )
    
    if same_choice:
        gain_diff = 0.0
    else:
        gain_diff = gain_roi - gain_score

    print(
        f"Différence progression : {gain_diff:+.1f}%"
    )

    print(
        f"Différence score : {score_gap:+.1f} points"
    )

    if score_gap >= 15:
        confidence = "ÉLEVÉE"
    elif score_gap >= 3:
        confidence = "MOYENNE"
    else:
        confidence = "FAIBLE"

    progress = project_progress(best_score["name"])
    remaining = project_remaining_hours(best_score["name"])

    chosen_future = future_engine.estimate (best_score["name"])
    alt_future = future_engine.estimate(best_roi["name"])
    chosen_risk = chosen_future.risk
    alt_risk = alt_future.risk


    render_strategic_summary(
    best_score=best_score,
    best_roi=best_roi,
    same_choice=same_choice,
    chosen_future=chosen_future,
    alt_future=alt_future,
    chosen_risk=chosen_risk,
    alt_risk=alt_risk,
    progress=progress,
    remaining=remaining,
    confidence=confidence,
    score_gap=score_gap,
    )

    render_postponement_risk(
    night_projects=night_projects,
    catalog=CATALOG,
    season_days_remaining=season_days_remaining,
    estimate_future_opportunities=future_engine.estimate,
    )

def show_roadmap(roadmap, night_capacities=None):

    show_multi_night_portfolio_roadmap(
    night_capacities=night_capacities
)

def build_dashboard_data(
    night,
    night_project,
    best_setup,
    best_filters,
    night_capacities=None
):
    if night_capacities is None:
        night_capacities = []

    total_capacity = forecast_available_hours(night_capacities)

    avg_capacity = (
        total_capacity / max(1, len(night_capacities))
        if night_capacities
        else 3.0
    )

    project_name = night_project["name"]
    remaining_hours = project_remaining_hours(project_name)

    remaining_nights = (
        remaining_hours / max(1, avg_capacity)
        if remaining_hours is not None
        else None
    )

    return {
        "recommended_project": project_name,
        "final_score": round(night_project.get("final_score", 0), 1),
        "astro_score": round(night_project.get("astro_score", 0), 1),
        "roi": round(night_project.get("roi", 0), 2),
        "remaining_hours": round(remaining_hours, 1) if remaining_hours is not None else None,
        "remaining_nights": round(remaining_nights, 1) if remaining_nights is not None else None,
        "best_setup": best_setup,
        "best_filters": best_filters,
        "future_capacity_hours": round(total_capacity, 1),
        "average_night_capacity": round(avg_capacity, 1),
    }

def average_night_capacity(nights):
    if not nights:
        return 1

    return (
        forecast_available_hours(nights)
        / max(1, len(nights))
    )

def show_action_plan(
    night,
    night_project,
    best_setup,
    best_filters,
    night_capacities=None
):
    
    if night_capacities is None :
        night_capacities = []

    dashboard_data = build_dashboard_data(
    night,
    night_project,
    best_setup,
    best_filters,
    night_capacities=night_capacities
)

    print("\n===== QUE FAIRE CE SOIR ? =====")

    window = night.get("best_window")

    if best_setup:
        print(f"1. Monter setup {best_setup['equipment']}")

    if best_filters:

        print(f"2. Charger filtre {best_filters[0]}")

    print(f"3. Pointer {night_project['name']}")

    if window:
        print(f"4. Commencer à {window['start']}")
        print(f"5. Fin prévue à {window['end']}")

        start = int(window["start"].split(":")[0])
        end = int(window["end"].split(":")[0])

        duration = end - start

        print(f"6. Temps disponible : {duration:.1f} h")

    print(f"7. ROI projet : {night_project['roi']:.2f}")

    progress = project_progress(night_project["name"])
    projects = get_projects()
    project_data = projects.get(night_project["name"], {})

    target_hours = project_data.get("target_hours", 0)

    if target_hours > 0:
        future_progress = min(
        100,
        progress + (100 * duration / target_hours)
    )
    else:
        future_progress = progress

    print(
        f"8. Progression après session : "
        f"{future_progress:.1f} %"
    )
    current_hours = project_data.get("hours", 0)

    remaining_after = max(
    0,
        target_hours - (current_hours + duration)
    )
    portfolio_gain = 0
    print(
        f"9. Temps restant après session : "
        f"{remaining_after:.1f} h"
    )
    if remaining_after <=0:
        print("10. Projet terminable ce soir : OUI")
    else:
        print("10. Projet terminable ce soir : NON")


    total_target = 0
    total_done_before = 0
    total_done_after = 0

    for name, project in projects.items():
        target = project.get("target_hours", 0)
        done = project.get("hours", 0)

        total_target += target
        total_done_before += done

        if name == night_project["name"]:
            done += duration

        total_done_after += min(done, target)

    portfolio_gain = 0
    next_project = next_project_after(
    night_project["name"]
    )

    if total_target > 0:
        portfolio_before = total_done_before / total_target * 100
        portfolio_after = total_done_after / total_target * 100
        portfolio_gain = portfolio_after - portfolio_before
        
    print(
        f"11. Gain portefeuille global : "
        f"+{portfolio_gain:.1f} %"
    )

    print(
        f"Portefeuille : "
        f"{portfolio_before:.1f}% -> "
        f"{portfolio_after:.1f}%"
    )

    hours_before = max(0, total_target - total_done_before)
    hours_after = max(0, total_target - total_done_after)

    if night_capacities:
        avg_night_hours = forecast_available_hours(night_capacities) / max(1, len(night_capacities))
    else:
        avg_night_hours = max(duration, 1)

    nights_before = hours_before / avg_night_hours
    nights_after = hours_after / avg_night_hours

    print("\n===== IMPACT DE CETTE NUIT =====")
    print(
        f"Progression portefeuille : "
        f"{portfolio_before:.1f}% → {portfolio_after:.1f}%"
    )

    print(
        f"Temps restant : "
        f"{hours_before:.1f} h → {hours_after:.1f} h"
    )

    print(
        f"Nuits restantes : "
        f"{nights_before:.1f} → {nights_after:.1f}"
    )
    
    night_projects = recommend_project_for_night(
        night["top_objects"],
        available_hours=night.get("duration", 3.0)
    )
    recommendation = night_projects[0]

    for reason in recommendation.get("reasons", []):
        print(f"✓ {reason}")

    print("\n===== STRATÉGIES =====")

    strategy_scores = recommendation.get("strategy_scores", {})

    for mode, score in strategy_scores.items():
        print(f"{mode:<16} : {score:.1f}")

    if len(night_projects) > 1:
        alternative = night_projects[1]

        chosen_gain = portfolio_gain_if_shot(
            night_project["name"],
            session_hours=night.get("duration", 3.0)
        )

        alt_gain = portfolio_gain_if_shot(
            alternative["name"],
            session_hours=night.get("duration", 3.0)
        )

        score_gap = (
            night_project["final_score"]
            - alternative["final_score"]
        )

        print("\nComparaison détaillée :")

        astro_gap = (
            night_project.get("astro_score", 0)
            - alternative.get("astro_score", 0)
        )

        print(f"Score astro choisi      : {night_project.get('astro_score', 0):.1f}")
        print(f"Score astro alternative : {alternative.get('astro_score', 0):.1f}")
        print(f"Différence astro        : {astro_gap:+.1f}")

        print(f"Score final choisi      : {night_project['final_score']:.1f}")
        print(f"Score final alternative : {alternative['final_score']:.1f}")
        print(f"Différence finale       : {score_gap:+.1f}")


        profile = load_user_profile()
        prefs = profile.get("preferences", {})

        astro_weight, project_weight = get_decision_weights()

        print("\nFacteurs dominants :")
        score_astro_weighted = night_project.get("astro_score", 0) * astro_weight
        priority_weighted = night_project.get("priority", 0) * project_weight
        altitude_bonus = night_project.get("altitude_bonus", 0)
        season_bonus = night_project.get("season_bonus", 0)
        roi_bonus = night_project.get("roi", 0) * 2
        closure_bonus = night_project.get("closure_bonus", 0)
        completion_bonus = night_project.get("completion_bonus", 0)

        print(f"Score astro pondéré : {score_astro_weighted:.1f}")
        print(f"Priorité pondérée   : {priority_weighted:.1f}")
        print(f"Bonus altitude      : {altitude_bonus:+.1f}")
        print(f"Bonus saison        : {season_bonus:+.1f}")
        setup_bonus = night_project.get("setup_score", 0)
        print(f"Score setup         : {setup_bonus:+.1f}")
        print(f"Bonus ROI           : {roi_bonus:+.1f}")
        print(f"Bonus clôture       : {closure_bonus:+.1f}")
        print(f"Bonus complétion    : {completion_bonus:+.1f}")

        print("-" * 30)
        print(f"Score final calculé : {night_project['final_score']:.1f}")

        alt_score_astro_weighted = alternative.get("astro_score", 0) * astro_weight
        alt_priority_weighted = alternative.get("priority", 0) * project_weight
        alt_setup_bonus = alternative.get("setup_score", 0)
        alt_altitude_bonus = alternative.get("altitude_bonus", 0)
        alt_season_bonus = alternative.get("season_bonus", 0)
        alt_roi_bonus = alternative.get("roi", 0) * 2
        alt_closure_bonus = alternative.get("closure_bonus", 0)
        alt_completion_bonus = alternative.get("completion_bonus", 0)

        if score_gap > 0:
            print(
                f"Décision : privilégier {night_project['name']} "
                f"(score supérieur de {score_gap:.1f} points)"
            )

            if alt_gain > chosen_gain:
                print(
                    "Note : l'alternative apporte davantage de progression "
                    "au portefeuille, mais le score global reste inférieur."
                )

        else:
            print("Décision : alternative compétitive")

        
        if next_project:

            print(
                f"12. Projet suivant recommandé : "
                f"{next_project['name']}"
                )
  
            next_roi = project_roi(next_project["name"])

            print(
                f"ROI : {next_roi:.2f}"
            )
            print(
                f"    Score : "
                f"{next_project['score']:.1f}"
            )

            print(
                f"    Temps restant : "
                f"{next_project['remaining']:.1f} h"
            )
            avg_capacity = average_night_capacity(night_capacities)

            estimated_nights = next_project["remaining"] / max(1, avg_capacity)


            print(
                f"Nuits restantes estimées : "
                f"{estimated_nights:.1f}"
            )

            print(f"- Score portefeuille : {next_project['score']:.1f}")
            print(f"- ROI : {next_roi:.2f}")
            print(f"- Temps restant : {next_project['remaining']:.1f} h")
            print(f"- Nuits estimées : {estimated_nights:.1f}")
            print(
                f"- Rang portefeuille : "
                f"#{next_project['rank']} / {next_project['total_projects']}"
            )
        print("\n=== APRÈS CETTE NUIT ===") 

        projects = get_projects()

        future_projects = []

        for name, project in projects.items():

            remaining = max(
                0,
                project["target_hours"] - project["hours"]
            )

            if remaining <= 0:
                continue

            if name == night_project["name"]:
                continue

            future_projects.append(
                (name, remaining, portfolio_score(name))
            )

        future_projects.sort(
            key=lambda x: x[2],
            reverse=True
        )

        for idx, (name, remaining, score) in enumerate(
            future_projects,
            start=1
        ):
            if remaining is None:
                remaining_txt = "inconnu"
            else:
                remaining_txt = f"{remaining:.1f} h"

            print(
                f"{idx}. {name} "
                f"(score {score:.1f}) "
                f"reste {remaining_txt}"
            )

        visible_obj = None

    for obj in night.get("top_objects", []):
        obj_key = obj.get("catalog_key", obj.get("name"))

        if obj_key == next_project["name"]:
            visible_obj = obj
            break

    print(
        f"- Visible ce soir : "
        f"{'OUI' if visible_obj else 'NON'}"
    )

    if visible_obj:
        print(f"- Altitude : {visible_obj.get('altitude', 0):.1f}°")
        print(f"- Score ciel : {visible_obj.get('global_score', 0):.1f}")
        print(f"\nTemps total restant : {hours_after:.1f} h")
        print(f"Nuits restantes estimées : {nights_after:.1f}")

    roadmap_before = portfolio_roadmap()
    roadmap_after = []

    available_hours = night_project.get("available_hours", 3.0)

    print("\n===== ROADMAP APRÈS CETTE NUIT =====")

    recommended_name = night_project["name"]

    for project in roadmap_before:

        remaining = project["remaining"]

        if project["name"] == recommended_name:
            remaining = max(
                0,
                remaining - available_hours
            )

        if remaining <= 0:
            roadmap_after.append({
                "name": project["name"],
                "remaining": 0,
                "roi": project["roi"],
                "nights": 0,
                "completed": True
            })
            continue

        roadmap_after.append({
                "name": project["name"],
                "remaining": remaining,
                "roi": project["roi"],
                "nights": estimate_remaining_nights(remaining, night_capacities),
                "completed": False
            })
    hours_after = 0

    for i, project in enumerate(roadmap_after, start=1):
        print(f"\n{i}. {project['name']}")

        if project.get("completed"):
            print("   TERMINÉ CETTE NUIT")
            continue

        print(f"   Reste : {project['remaining']:.1f} h")
        print(f"   ROI : {project['roi']:.2f}")
        gain = session_portfolio_gain(project["name"], available_hours)
        print(f"   Gain projet session : +{gain:.1f}%")
        print(f"   Nuits estimées : {project['nights']:.1f}")
        hours_after += project["remaining"]

    print("\n==============================")
    print(f"Temps total restant : {hours_after:.1f} h")
    print(f"Nuits restantes estimées : {hours_after / max(1, avg_capacity):.1f}")

    print("\n=============================")

def show_portfolio_dashboard():
    
    projects = get_projects()

    if not projects:
        print("\nAucun projet enregistré")
        return

    total_done = 0
    total_target = 0

    print("\n===== PORTEFEUILLE ASTRO =====\n")

    for name, project in projects.items():
        hours = project.get("hours", 0)
        target = project.get("target_hours", 0)
        remaining = max(0, target - hours)

        progress = 0
        if target > 0:
            progress = round(hours / target * 100, 1)

        total_done += hours
        total_target += target

        print(
            f"{name:15} "
            f"{hours:5.1f} / {target:5.1f} h "
            f"{progress:5.1f}% "
            f"reste {remaining:5.1f} h"
        )
        total_done = 0
        total_target = 0

    for name, project in projects.items():
        done = project.get("hours", 0)
        target = project.get("target_hours", 0)

        total_done += done
        total_target += target
        total_remaining = max(0, total_target - total_done)

        global_progress = 0
    if total_target > 0:
        global_progress = round(total_done / total_target * 100, 1)
    print(f"Heures cibles : {total_target:.1f} h")

    print("\n----- TOTAL -----")
    print(f"Heures réalisées : {total_done:.1f} h")
    print(f"Heures cibles : {total_target:.1f} h")
    print(f"Heures restantes : {total_remaining:.1f} h")
    nights = estimate_portfolio_nights()
    print(f"Nuits restantes estimées : {nights}")
    print(f"Progression globale : {global_progress:.1f}%")


def session_portfolio_gain(name, session_hours=3.0):
    remaining = project_remaining_hours(name)

    if remaining is None or remaining <= 0:
        return 0

    gain_hours = min(session_hours, remaining)

    project = get_projects().get(name, {})
    project_total = project.get("target_hours", 0)

    if project_total <= 0:
        return 0

    gain_percent = (gain_hours / project_total) * 100

    return gain_percent

def portfolio_score(name):
    priority = project_priority(name)

    obj = CATALOG.get(name, {})

    urgency = urgency_bonus(obj)
    season = season_window_bonus(obj)
    roi = project_roi(name)

    progress = project_progress(name)
    completion = progress / 5

    closure = closure_bonus(name)

    return (
        priority * 0.6
        + urgency
        + season
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

        obj = CATALOG.get(name, {})

        altitude = urgency_bonus(obj)
        season = season_window_bonus(obj)
        roi = project_roi(name)

        progress = project_progress(name)
        completion = progress / 5
        closure = closure_bonus(name)
        score = (
            priority * 0.6
            + altitude
            + season
            + min(roi * 5, 20)
            + completion
            + closure
        )

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

def show_completion_forecast():

    projects = get_projects()

    roadmap = []

    if not projects:
        return

    capacity = forecast_available_hours(
        sorted(nights, key=lambda x: x["score"], reverse=True)[:3]
    )
    best_nights = sorted(
        nights,
        key=lambda x: x["score"],
        reverse=True
    )

    for name in projects:
        score = portfolio_score(name)
        progress = project_progress(name)
        remaining = project_remaining_hours(name)

        progress = project_progress(name)
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
    avg_capacity = averaage_night_capacity(best_nights)
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

def show_astro_calendar():
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

    project["hours_done"] = min(target, project.get("hours_done",project.get("hours",0)) + hours)
    
    project.get("hours", 0)+ hours

    project["remaining"] = max(
        0,
        target - project["hours_done"]
    )
    project["progress"] = round(project["hours_done"] / target *100, 1) if target > 0 else 0
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

        
    ###############################print("\n===== DATES DE FIN SIMULÉES =====")

    ##############################unfinished_projects = []

    #############################for name, project in projects.items():
        ############################done = project.get("hours_done", project.get("hours", 0))
        ###########################target = project.get("target_hours", 0)
        ##########################remaining = max(0, target - done)

        #########################if remaining > 0:
            #####################unfinished_projects.append(name)

        ########################avg_night_hours = (
            ####################sum(n.get("duration", 3.0) for n in nights) / len(nights)
            ###################if nights else 3.0
        ##################)

        #################unfinished_hours = sum(
            ################remaining_by_name.get(name, 0)
            ###############for name in unfinished_projects
        ##############)

        #############extra_nights = math.ceil(unfinished_hours / avg_night_hours) if avg_night_hours > 0 else 0

        ############if unfinished_projects and completion_dates:
            ###########last_known_date = max(completion_dates.values())
            ##########portfolio_end = (
                #########datetime.strptime(last_known_date, "%Y-%m-%d")
                ########+ timedelta(days=extra_nights)
            #######).strftime("%Y-%m-%d")
        ######elif completion_dates:
            #####portfolio_end = max(completion_dates.values())
        ####else:
            ###portfolio_end = "Indéterminée"


    ##for name, date in completion_dates.items():
            #print(f"{name} -> {date}")

    #print("\n===== FIN PORTEFEUILLE =====")
    #print(f"Date estimée : {portfolio_end}")

    return {
    "completion_dates": completion_dates,
    "portfolio_end": None,
    "unfinished_projects": [],
    "remaining_hours": {},
    "unfinished_hours": 0,
    "extra_nights": 0,
    "avg_night_hours": nights,
}

def hour_score(hour, moon_illumination, moon_visible, moon_elevation, moon_target_sep, target_altitude, bortle=4, target="deep_sky", target_object=None, goal="balanced"):
    penalty = 0

    sky = SkyEngine()

    bp = sky.bortle_penalty(bortle)
    cp = sky.cloud_penalty(
    hour["cloud_cover"],
    hour["cloud_cover_low"],
    hour["cloud_cover_mid"],
    hour["cloud_cover_high"]
    )
    
    mp = sky.moon_penalty(moon_illumination, moon_elevation, moon_target_sep)

    sqm = estimated_sqm(
    bortle,
    moon_illumination,
    moon_elevation,
    moon_target_sep)
    
    target_bonus = 0

    if target_object is not None:
        obj = CATALOG.get(target_object)

        if obj and obj["type"] in favorite_targets():
            target_bonus += 10
                
    if target_altitude > 80:
        target_bonus += 15
    elif target_altitude > 70:
        target_bonus += 7
    elif target_altitude > 60:
        target_bonus += 4
    elif target_altitude > 45:
        target_bonus += 2
    elif target_altitude > 30:
        target_bonus += -0
    elif target_altitude > 20:
        target_bonus += -5
    else:
        target_bonus += -15
          
    if moon_elevation <= 0:
        mp = 0
    elif moon_elevation < 10:
        mp *= 0.4
    elif moon_elevation < 20:
        mp *= 0.7
    elif moon_elevation < 35:
        mp *= 1.0
    #elif moon_elevation < 20:
        #mp *= 0.80
    #elif moon_elevation < 35:
        #mp *= 0.95
    else:
        mp *= 1.4

    if mp < 5:
        moon_impact = "nul"
    elif mp < 15:
        moon_impact = "faible"
    elif mp < 30:
        moon_impact = "modéré"
    elif mp < 50:
        moon_impact = "fort"
    else:
        moon_impact = "très fort"
    
    hp = sky.humidity_penalty(hour["relative_humidity_2m"])
    pp = sky.precipitation_penalty(hour["precipitation"])
    wp = sky.wind_penalty(hour["wind_speed_10m"])
    vp = sky.visibility_penalty(hour.get("visibility"))
    tb = sky.temperature_bonus(hour["temperature_2m"])
   
    profile = TARGETS[target]

    penalty = (
        cp * profile["cloud"] +
        mp * profile["moon"] +
        hp * profile["humidity"] +
        pp * profile["precip"] +
        wp * profile["wind"] +
        vp * profile["visibility"] +
        bp * profile["bortle"] 
    )
    sqm_bonus = max(-10, min(20,(sqm - 20.5)*12))

    if sqm >= 21.5:
        sqm_bonus = 4
    elif sqm >= 21.3:
        sqm_bonus = 2
    elif sqm >= 21.0:
        sqm_bonus = 0
    elif sqm >= 20.7:
        sqm_bonus = -2
    else:
        sqm_bonus = -5
        
    obj_meta = CATALOG.get(target_object, {})
    obj_type = obj_meta.get("type", "unknown")

    equipment_result = compare_object_to_equipment(
    obj_meta.get("size_arcmin", 20),
    obj_type
    )
    equipment_score = equipment_result["equipment_score"]
    frame_bonus = equipment_result["frame_bonus"]

    target_bonus = frame_bonus

    if goal in ["nebulae", "nebula"] and "nebula" in obj_type:
        target_bonus += 12

    elif goal in ["galaxies", "galaxy"] and "galaxy" in obj_type:
        target_bonus += 12

    elif goal in ["clusters", "cluster"] and "cluster" in obj_type:
        target_bonus += 12

    project_bonus = portfolio_score(target_object)

    priority_bonus=( 
    project_priority(target_object) * 0.3)

    season = season_bonus({
        "catalog_key": target_object
    })

    score = round(
        max(
        0,
        min(
            100,
            45 - penalty + tb + target_bonus + sqm_bonus + project_bonus + priority_bonus + season
        )
    )
)

    details = {
    "moon": round(mp * profile["moon"], 1),
    "cloud": round(cp * profile["cloud"], 1),
    "humidity": round(hp * profile["humidity"], 1),
    "precip": round(pp * profile["precip"], 1),
    "wind": round(wp * profile["wind"], 1),
    "visibility": round(vp * profile["visibility"], 1),
    "bortle": round(bp * profile["bortle"], 1),
    "moon_sep": round(moon_target_sep, 1),
    "target_altitude": round(target_altitude, 1),
    "sqm": sqm,
    "score_final": score,
    "frame_bonus": frame_bonus,
    "target_bonus": target_bonus,
    "temperature_bonus": tb,
    "penalty": round(penalty, 1),
    "project_bonus": project_bonus,
    "priority_bonus": round(priority_bonus, 1),
    "season_bonus" : season,
    
}
    
    if mp < 5:
        moon_impact = "nul"
    elif mp < 15:
        moon_impact = "faible"
    elif mp < 30:
        moon_impact = "modéré"
    elif mp < 50:
        moon_impact = "fort"
    else:
        moon_impact = "très fort"

    return {
        "score": score,
        "details": details,
        "moon_impact": moon_impact,
        "moon_penalty": round (mp, 1),
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

    print(f"\nComparaison matériel pour {object_name}\n")

    results = []

    for eq_name in list_equipment():
        set_current_equipment(eq_name)

        result = compare_object_to_equipment(
            obj.get("size_arcmin", 20),
            obj.get("type", "unknown"),
            obj.get("scale", "medium"),
        )
        img_score = imaging_score(obj)
        cap_score = capture_score(eq_name)

        final_score = (
            result["combined_score"] * 0.55 +
            img_score * 0.20 +
            cap_score * 0.25
        )
        results.append({
            "equipment": eq_name,
            "score": round(final_score),
            "equipment_score": result["equipment_score"],
            "resolution_score": result["resolution_score"],
            "ratio": result["ratio"],
            "frame_bonus": result["frame_bonus"],
            "arcsec_pixel": result["arcsec_pixel"],
            "imaging_score": img_score,
            "cap_score": cap_score,
        })
    results.sort(key=lambda x: x["score"], reverse=True)

    print(f"Object : {CATALOG[object_name]['name']}")
    print(f"Taille : {CATALOG[object_name]['size_arcmin']} arcmin")

    for r in results:
        print(
            f"{r['equipment']:25} "
            f"score={r['score']:3} "
            f"frame={r['frame_bonus']:2} "
            f"ratio={r['ratio']:.3f} "
            f"res={r['arcsec_pixel']}"
            f"eq={r['equipment_score']}"
            f" resS={r['resolution_score']}"
            f" img={r['imaging_score']}",
            f" cap={r['cap_score']}",
        )
def best_setup_for_object(object_name):
    obj = CATALOG.get(object_name)

    if not obj:
        return []

    results = []

    for eq_name in list_equipment():
        set_current_equipment(eq_name)

        result = compare_object_to_equipment(
            obj.get("size_arcmin", 20),
            obj.get("type", "unknown"),
            obj.get("scale", "medium"),
        )

        img_score = imaging_score(obj)
        cap_score = capture_score(eq_name)

        final_score = (
            result["combined_score"] * 0.70 +
            img_score * 0.15 +
            cap_score * 0.15
        )

        results.append({
            "equipment": eq_name,
            "score": round(final_score),
            "equipment_score": 
        result["equipment_score"],
            "resolution_score":
        result["resolution_score"],
            "frame_bonus": result["frame_bonus"],
            "ratio": result["ratio"],
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    return results

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

        pixel_um = setup.get("pixel_size_um") or setup.get("pixel_size_mm")

        if pixel_um is None and setup_name == "samyang_183":
            pixel_um = 2.4

        arcsec_pixel = (
            round(206.265 * pixel_um / setup.get("focal_length_mm"), 2)
            if setup.get("focal_length_mm") and pixel_um
            else None
        )

        s= setup_result["score"]
        reasons = setup_result["reasons"]

        setup_ranking.append({
            "setup": setup_name,
            "score": s,
            "reasons": reasons,
            "arcsec_pixel": arcsec_pixel,

        })

        if s > best_setup_score:
            best_setup_score = s
            best_setup = setup_name

    setup_ranking.sort(key=lambda x: x["score"], reverse=True)
    best["best_setup"] = best_setup
    best["setup_score"] = best_setup_score
    best["global_score"] = best["score"] + best_setup_score

    best["setup_reasons"] = setup_ranking[0].get("reasons", []) if setup_ranking else []

    best["arcsec_pixel"] = setup_ranking[0].get("arcsec_pixel") if setup_ranking else None

    progress = project_progress(obj_name)
    remaining_hours = project_remaining_hours(obj_name)
    roi = project_roi(obj_name)

   
    progress = project_progress(obj_name)
    remaining_hours = project_remaining_hours(obj_name)
    roi = project_roi(obj_name)

    altitude = best.get("target_altitude")

    if altitude is not None:

        decision_engine = DecisionEngine()
        decision_engine.add_rule(AltitudeRule())
        decision_engine.add_rule(MoonRule())
        decision_engine.add_rule(CloudRule())
        decision_engine.add_rule(HumidityRule())
        decision_engine.add_rule(WindRule())
        decision_engine.add_rule(VisibilityRule())
        decision_engine.add_rule(SeeingRule())
        decision_engine.add_rule(SamplingRule())
        decision_engine.add_rule(ResolutionRule())
        decision_engine.add_rule(ImageQualityRule())
        decision_engine.add_rule(ObjectFitRule())

        ####print(">>> ResolutionRule ajoutée")
        ###print(decision_engine.rules)

        clouds = best.get("clouds", 0)

        ##print(best.keys())
        #print(best.get("setup_ranking"))


        camera = Camera(
            manufacturer="ZWO",
            model="ASI183MM",
            pixel_size_um=2.4,
            sensor_width_px=5496,
            sensor_height_px=3672,
            monochrome=True,
        )

        optics = ImagingOptics(
            manufacturer="Samyang",
            model="135mm",
            focal_length_mm=135,
            aperture_mm=48,
            focal_ratio=2.8,
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
            visibility=best.get("visibility", best.get("visibility_m", 0)),
        )

        sky_context = SkyContext(
            target=target,
            moon_illumination=illumination,
            moon_separation_deg=best.get("moon_sep", 180),
            target_altitude_deg=altitude,
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
            astro_weight=profile.get("preferences", {}).get("astro_weight", 0.7),
            project_weight=profile.get("preferences", {}).get("project_weight", 0.3),
            minimum_altitude_deg=profile.get("preferences", {}).get("minimum_altitude_deg", 30),
            minimum_sqm=profile.get("preferences", {}).get("min_sqm", 20),
        )

        decision_context = DecisionContext(
            session=session_context,
            site=site_context,
            equipment=equipment_context,
            weather=weather_context,
            sky=sky_context,
            portfolio=portfolio_context,
            preferences=preferences_context,
        )

        context = {
            "altitude": altitude,
            "illumination": illumination,
            "moon_elevation": best.get("moon_elevation"),
            "moon_sep": best.get("moon_sep"),
            "cloud_cover": clouds,
            "cloud_cover_low": clouds,
            "cloud_cover_mid": clouds,
            "cloud_cover_high": clouds,
            "humidity" : best.get("humidity", 0),
            "wind": best.get("wind", 0),
            "visibility": best.get("visibility", best.get("visibility_m",0)),
            "seeing" : best.get("seeing"),
            "sampling": best.get("arcsec_pixel"),
            "object_type": CATALOG.get(obj_name, {}).get("type"),
            "object_size_arcmin": CATALOG.get(obj_name, {}).get("size_arcmin"),
            "object_name": obj_name,
        }

        contributions, decision_score = decision_engine.evaluate(
            decision_context,
            profile,
        )

        from decision.engines.decision_summary_engine import DecisionSummaryEngine

        summary = DecisionSummaryEngine.build(contributions)

        from decision.recommendation.alternative_target_engine import AlternativeTargetEngine

    priority = profile.get("project_priorities", {}).get(obj_name, 0)
    
    result = {
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
        "progress": progress,
        "remaining_hours": remaining_hours,
        "roi": roi,
        "priority": priority,
        "season_bonus": best.get("season_bonus", 0),
        "weather_bonus": best.get("weather_bonus", 0),
        "decision_summary": summary,
        "decision_context": decision_context,
        "weather_context": weather,
    }

    return result

def build_night_result():
    return {
        "date": str(night_date),
            "score": night_score,
            "moon_impact": best["moon_impact"],
            "moon_penalty": best["moon_penalty"],
            "verdict": verdict(night_score),
            "bortle": bortle,
            "object": best_object,
            "best_setup": setup_name,
            "setup_score": best_results[0].get("setup_score", 0),
            "global_score": best_results[0].get("global_score", 0),
            "best_object_score": all_results[0]["global_score"],
            "all_objects": all_results,
    
            "best_objects": [
                r["name"]
                for r in top3
                if r["score"] == best_score
            ]
    }
    

def build_night_schedule_legacy(objects, available_hours, profile=None):
    schedule = []
    remaining = available_hours
    current_time = 0

    for obj in objects:
        if remaining <= 0:
            break

        duration = min(
            obj.get("remaining_hours", remaining),
            remaining
        )

        schedule.append({
            "object": obj["name"],
            "hours": duration,
            "start" : current_time,
            "end": current_time + duration,
            "score": obj.get("global_score", obj.get("score", 0)),
            "setup": obj.get("best_setup"),
        })

        remaining -= duration
        current_time += duration

    return schedule

def forecast_astro(
    lat,
    lon,
    city,
    bortle,
    target="deep_sky",
    equipment=None,
    goal="nebulae"
):
    if equipment is None:
        equipment = equipment or get_active_equipment()

    try:
        weather = fetch_weather(lat, lon)
    except Exception as e:
        print("ERREUR fetch_weather =", repr(e))
        weather = None

    if weather is None:
        print("ERREUR : prévisions météo indisponibles.")
        print("Recommandation météo réelle impossible.")
        return []
    else:
        rows = parse_hourly_weather(weather)

        from decision.weather.weather_forecast import WeatherForecast
        caps=WeatherForecast(
            hourly=rows,
            hourly_clouds=[h.get("cloud_cover",
                100) for h in rows],
            hourly_temperature=[h.get("temperature_2m",0) for h in rows],
            hourly_visibility=[h.get("visibiility", 10000) for h in rows],
            hourly_humidity=[h.get("relative_humidity_2m", 100) for h in rows],
            hourly_wind=[h.get("wind_speed_10m", 0) for h in rows],
        )

    results = []

    #print("TARGET_OBJECTS = ", TARGET_OBJECTS)

    today = datetime.now(ZoneInfo(TIMEZONE)).date()

    for d in range(7):
        night_date = today + timedelta(days=d)
        current_date = datetime.combine(night_date, datetime.min.time())

        phase = moon_phase(current_date.date())

        sky = SkyEngine()

        illumination = round(sky.moon_illumination_from_phase(phase))


        city_info = LocationInfo(city, "Switzerland", TIMEZONE, lat, lon)

        target_date = current_date.date()

        sky = SkyEngine()

        moon_rise = sky.safe_moonrise(city_info.observer, target_date, ZoneInfo(TIMEZONE))
        moon_set  = sky.safe_moonset(city_info.observer, target_date, ZoneInfo(TIMEZONE))


        hours = night_hours_rough(rows, current_date, lat, lon, city)

        if not hours:
            continue

        profile = load_user_profile()
        decision_engine = DecisionEngine()
        decision_engine.add_rule(AltitudeRule())
    
        all_results = []

        from decision.weather.weather_forecast import WeatherForecast

        caps = WeatherForecast(
            hourly=rows,
            hourly_clouds=[h.get("cloud_cover", 100) for h in rows],
            hourly_humidity=[h.get("relative_humidity_2m", 100) for h in rows],
            hourly_wind=[h.get("wind_speed_10m", 0) for h in rows],
            hourly_temperature=[h.get("temperature_2m", 0) for h in rows],
            hourly_visibility=[h.get("visibility", 10000) for h in rows],
        )

        for obj_name in TARGET_OBJECTS:

            result = evaluate_object(
                obj_name=obj_name,
                sky=sky,
                hours=hours,
                weather=caps,
                illumination=illumination,
                moon_rise=moon_rise,
                moon_set=moon_set,
                city_info=city_info,
                lat=lat,
                lon=lon,
                bortle=bortle,
                target=target,
                profile=profile,
            )

            if result is not None:
                all_results.append(result)

            if result is not None:
                altitude = result.get("target_altitude")

                if altitude is not None:
                    contributions = decision_engine.evaluate(
                        {"altitude": altitude},
                        profile,
                    )

        if not all_results:
            continue

        all_results.sort(key=lambda x: x["global_score"], reverse=True)
        best_score = all_results[0]["global_score"]

        top3 = all_results[:3]

        best_results = all_results[:3]

        from decision.recommendation.alternative_target_engine import AlternativeTargetEngine

        best_object = best_results[0]["name"]

        alternatives = AlternativeTargetEngine.recommend(
            current_target=best_object,
            ranked_targets=best_results,
        )

        for r in best_results:
            name = r["name"]
            r["priority"] = project_priority(name)
            r["progress"] = project_progress(name)
            r["remaining_hours"] = project_remaining_hours(name)
            r["roi"] = project_roi(name)

        strategy_engine = NightStrategy(profile)

        strategy = strategy_engine.choose_strategy(
            best_results,
            sum(h.get("hours", 0) for h in hours)
        )

        strategy = strategy_engine.choose_strategy(
            best_results,
            sum(h.get("hours", 0) for h in hours)
        )

        best = best_results[0]["window"]
        best_object = best_results[0]["name"]


        best_setup = best_setup_for_object(best_object)

        setup_name = best_results[0].get("best_setup", "inconnu")

        exposure = recommended_exposure(
            CATALOG[best_object],
            bortle=bortle
        )       

        all_results = sorted(
            all_results,
            key=lambda x: x["global_score"],
            reverse=True
        )

        top3 = all_results[:3]
        top5 = all_results[:5]
        night_score = round(
            sum(r["global_score"] for r in top3) / len(top3)
)

        portfolio_keys = set(get_projects().keys())

        top_objects_for_night = all_results[:5]

        portfolio_objects = [
        r for r in all_results
        if r.get("catalog_key", r.get("name")) in portfolio_keys
        ]

        for r in portfolio_objects:
            if r not in top_objects_for_night:
                top_objects_for_night.append(r)

        results.append({
            "date": str(night_date),
            "score": night_score,
            "moon_impact": best["moon_impact"],
            "moon_penalty": best["moon_penalty"],
            "verdict": verdict(night_score),
            "bortle": bortle,
            "object": best_object,
            "best_setup": setup_name,
            "setup_score": best_results[0].get("setup_score", 0),
            "global_score": best_results[0].get("global_score", 0),
            "best_object_score": all_results[0]["global_score"],
            "all_objects": all_results,
    
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
                    "altitude": round(float(r["window"]["target_altitude"]), 1),
                    "moon_sep": round(float(r["window"]["moon_sep"]), 1),
                    "sqm": round(float(r["window"]["sqm"]), 2),
                    "moon_score": round(float(r["window"]["details"][0]["moon"]), 1),
                    "frame_bonus": round(float(r["window"]["details"][0]["frame_bonus"]), 1),
                    "project_bonus": round(float(r["window"]["details"][0].get("project_bonus", 0)), 1),
                    "remaining_hours":project_remaining_hours(r["catalog_key"]),
                    "priority_bonus": round(float(r["window"]["details"][0].get("priority_bonus", 0)),),
                    "best_setup": r.get("best_setup"),
                    "setup_score": r.get("setup_score", 0),
                    "global_score": r.get("global_score", r["score"]),
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
                for w in all_results[0]["window"].get("top_windows", [best])
            ],
            "moon": {
                "illumination": illumination,
                "rise": moon_rise.strftime("%H:%M") if moon_rise else None,
                "set": moon_set.strftime("%H:%M") if moon_set else None,
            },
            "weather_summary": {
                "cloud_cover_percent": round(
                    sum(h["cloud_cover"] for h in hours) / len(hours)
                ),
                "humidity_percent": round(
                    sum(h["relative_humidity_2m"] for h in hours) / len(hours)
                ),
                "wind_kmh": round(
                    sum(h["wind_speed_10m"] for h in hours) / len(hours),
                    1
                ),
            }
        })

    return results


def fake_clear_weather():
    rows = []
    now = datetime.now(ZoneInfo(TIMEZONE))

    for i in range(24 * 7):
        rows.append({
            "time": now + timedelta(hours=i),
            "cloud_cover": 0,
            "cloud_cover_low": 0,
            "cloud_cover_mid": 0,
            "cloud_cover_high": 0,
            "precipitation": 0,
            "relative_humidity_2m": 50,
            "visibility": 20000,
            "wind_speed_10m": 5,
            "temperature_2m": 10,
        })

    return rows

def get_location_by_ip():
    try:
        r = requests.get("https://ipapi.co/json/", timeout=10)
        r.raise_for_status()
        data = r.json()

        return {
            "lat": float(data["latitude"]),
            "lon": float(data["longitude"]),
            "city": data.get("city", "Lieu détecté"),
            "country": data.get("country_name", ""),
        }

    except Exception:
        return {
            "lat": 46.7508,
            "lon": 6.5495,
            "city": "Buttes",
            "country": "Switzerland",
        }
def decision_score(astro_score, portfolio_score, profile):
    prefs = profile.get("preferences", {})

    astro_weight = prefs.get("astro_weight", 0.7)
    project_weight = prefs.get("project_weight", 0.3)

    return (
        astro_score * astro_weight +
        portfolio_score * project_weight
    )

def get_future_night_capacities(nights, max_nights=10):
    top_nights = sorted(
        nights,
        key=lambda x: x["score"],
        reverse=True

    )[:max_nights]

    capacities = []

    for night in top_nights:
        window = night.get("best_window")

        if window:
            start = int(window["start"].split(":")[0])
            end = int(window["end"].split(":")[0])
            duration = end - start
        else:
            duration = 0

        capacities.append({
            "date": night.get("date"),
            "hours": max(0, duration),
            "score": night.get("score", 0),
        })

    capacities.sort(
        key=lambda x: x["date"]
    )
    return capacities

def best_equipment_for_object(object_name):
    obj = CATALOG.get(object_name)

    if not obj:
        return None

    results = []

    for eq_name in list_equipment():
        set_current_equipment(eq_name)

        result = compare_object_to_equipment(
            obj.get("size_arcmin", 20),
            obj.get("type", "unknown"),
            obj.get("scale", "medium"),
        )

        results.append({
            "equipment": eq_name,
            "score": result["combined_score"],
        })

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[0]

future_engine = FutureOpportunityEngine(
    catalog=CATALOG,
    weather_provider=fetch_weather,
    season_engine=season_days_remaining,
    profile_provider=load_user_profile,
    project_provider=project_remaining_hours,
)

if __name__ == "__main__":
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

    args = parser.parse_args()

    if args.object:
        compare_equipment_for_object(args.object)
        exit()

    if args.target_object:
        obj_key = args.target_object
        obj = CATALOG.get(obj_key)

        if not obj:
            print(f"Objet inconnu : {obj_key}")
            exit()

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

        exit()

    location = get_default_location()
    lat = location["latitude"]
    lon = location["longitude"]
    city = location["name"]

    print(f"\nLieu détecté : {city} ({lat}, {lon})\n")

    weather = fetch_weather(lat, lon)
    
    if weather is None:
        print ("Prévisions météo indisponibles.")
        nights=[]
    else:
        rows = parse_hourly_weather(weather)
    
    
        bortle = 3
        target = "deep_sky"
    user_profile = load_user_profile()
    selected_equipment = args.equipment or get_active_equipment()
    
    nights = forecast_astro(
        lat,
        lon,
        city,
        bortle=3,
        target=TARGET,
        equipment=args.equipment,
        goal=args.goal
    )

    if nights is None:
        print("ERREUR: forecast_astro a retourné None")
        exit()

    top_nights = sorted(nights, key=lambda x: x["score"], reverse=True)[:3]

night_capacities = forecast_night_capacities(lat, lon)

print("\n===== CAPACITÉ À VENIR =====")

total_capacity = sum(c["hours"] for c in night_capacities)

for c in night_capacities:
    print(f"{c['date']} : {c['hours']:.1f} h qualité={c['quality']:.0f}")

print(f"Total prévisionnel : {total_capacity:.1f} h")

if args.mode == "portfolio":
    show_portfolio_ranking()
    show_completion_forecast()

elif args.mode == "calendar":
    show_astro_calendar()
    roadmap = simulate_portfolio_calendar(nights)

elif args.mode == "tonight":
    if top_nights:
        winner = top_nights[0]
        top_objects = winner.get("top_objects") or []

        available_hours = winner.get("duration", 3.0)

        recommended_projects = recommend_project_for_night(
            top_objects,
            available_hours=available_hours,
        )

        if recommended_projects:
            recommended_project = recommended_projects[0]
            recommended_key = recommended_project.get(
                "catalog_key",
                recommended_project.get("name"),
            )

            mission_source = next(
                (
                    obj
                    for obj in top_objects
                    if obj.get("catalog_key", obj.get("name")) == recommended_key
                ),
                None,
            )

            if mission_source is None:
                print(
                    f"\nMission impossible à construire : "
                    f"contextes introuvables pour {recommended_key}"
                )
            else:
                mission = NightMissionBuilder.build(
                    target=mission_source["name"],
                    summary=mission_source["decision_summary"],
                    context=mission_source["decision_context"],
                    weather=mission_source["weather_context"],
                )

                MissionPresenter.present(mission)

        dynamic_roadmap = simulate_dynamic_portfolio_roadmap(
            night_capacities=night_capacities)
        show_portfolio_completion_forecast(dynamic_roadmap)

    if USE_LEGACY_TONIGHT_REPORT :
        show_tonight_recommendation(top_nights[0])

elif args.mode == "full":
    show_portfolio_ranking()
    #show_completion_forecast()
    show_astro_calendar()
    roadmap = simulate_portfolio_calendar(nights)
    show_roadmap(roadmap, night_capacities=night_capacities)
    dynamic_roadmap = simulate_dynamic_portfolio_roadmap(
    night_capacities=night_capacities)
    show_portfolio_completion_forecast(dynamic_roadmap)
    if top_nights:
        if USE_LEGACY_TONIGHT_REPORT:
            show_tonight_recommendation(top_nights[0])

    