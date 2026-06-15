import sys
import math
import json
import requests
import warnings
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
from astropy.coordinates.baseframe import NonRotationTransformationWarning
from astropilot.catalog import CATALOG
from astropilot.equipment_profiles import CURRENT_EQUIPMENT, get_fov
from astropilot.equipment_profiles import equipment_match_score
from astropilot.equipment_profiles import capture_score
from astropilot.user_profile import (get_default_location, load_user_profile, favorite_targets, get_available_equipment, get_preferences, get_projects,)
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
    "seestar_s50": {
        "name": "Seestar S50",
        "focal_length_mm": 250,
        "aperture_mm": 50,
        "sensor_width_mm": 5.6,
        "sensor_height_mm": 3.2,
    },

    "widefield_135mm": {
        "name": "APS-C + 135 mm",
        "focal_length_mm": 135,
        "aperture_mm": 50,
        "sensor_width_mm": 22.3,
        "sensor_height_mm": 14.9,
    },

    "newton_150_750": {
        "name": "Newton 150/750 APS-C",
        "focal_length_mm": 750,
        "aperture_mm": 150,
        "sensor_width_mm": 22.3,
        "sensor_height_mm": 14.9,
    },
}



CURRENT_EQUIPMENT = "widefield_135mm"


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


def safe_moonrise(observer, date, tz):
    try:
        return moonrise(observer, date, tzinfo=tz)
    except ValueError:
        return None

def safe_moonset(observer, date, tz):
    try:
        return moonset(observer, date, tzinfo=tz)
    except ValueError:
        return None

def fetch_weather(lat: float, lon: float) -> dict | None:
    url = "https://api.open-meteo.com/v1/forecast"

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
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.ReadTimeout:
        print("Erreur météo : timeout Open-Meteo")
        return None

    except requests.exceptions.HTTPError as e:
        print(f"Erreur HTTP Open-Meteo : {e}")
        return None

    except Exception as e:
        print(f"Erreur météo : {e}")
        return None

def cloud_penalty(total, low, mid, high):

    weighted = (
        low * 0.2 +
        mid * 0.3 +
        high * 0.5
    )

    if weighted < 10:
        return 0
    if weighted < 20:
        return 3
    if weighted < 30:
        return 8
    if weighted < 40:
        return 15
    if weighted < 60:
        return 22
    if weighted < 80:
        return 35
    return 50


def temperature_bonus(temp):

    if 8 <= temp <= 18:
        return 5

    if 0 <= temp < 8:
        return 2

    if temp > 18:
        return 2

    return 0

def moon_illumination_from_phase(phase: float) -> float:
    """
    Astral renvoie une phase entre 0 et environ 29.5 jours.
    0 = nouvelle lune
    14-15 = pleine lune
    """

    normalized = phase / 29.53
    illum = (1 - math.cos(2 * math.pi * normalized)) / 2

    return illum * 100

def moon_target_separation(target_ra, target_dec, obs_time, lat, lon):
    location = EarthLocation(
        lat=lat * u.deg,
        lon=lon * u.deg
    )

    target = SkyCoord(
        ra=target_ra * u.deg,
        dec=target_dec * u.deg
    )

    moon_pos = get_body(
        "moon",
        Time(obs_time),
        location=location
    )

    return target.separation(moon_pos).deg

def target_altitude(target_ra, target_dec, obs_time, lat, lon):

    location = EarthLocation(
        lat=lat * u.deg,
        lon=lon * u.deg
    )

    target = SkyCoord(
        ra=target_ra * u.deg,
        dec=target_dec * u.deg
    )

    frame = AltAz(
        obstime=Time(obs_time),
        location=location
    )

    return target.transform_to(frame).alt.deg

def target_altitude_bonus(alt):
    if alt >= 75:
        return 25
    elif alt >= 60:
        return 18
    elif alt >= 45:
        return 10
    elif alt >= 20:
        return -15
    else:
        return -35
    
def moon_penalty(illumination, moon_elevation, moon_sep):

    if moon_elevation <= -6:
        return 0

    illum_factor = illumination / 100.0

    if moon_elevation <= 0:
        elev_factor = 0.05
    elif moon_elevation < 10:
        elev_factor = 0.20
    elif moon_elevation < 25:
        elev_factor = 0.45
    elif moon_elevation < 45:
        elev_factor = 0.75
    else:
        elev_factor = 1.0

    if moon_sep >= 150:
        sep_factor = 0.15
    elif moon_sep >= 120:
        sep_factor = 0.30
    elif moon_sep >= 90:
        sep_factor = 0.55
    elif moon_sep >= 60:
        sep_factor = 0.80
    else:
        sep_factor = 1.0

    return round(35 * illum_factor * elev_factor * sep_factor, 1)

def moon_phase_name(illumination):

    if illumination < 5:
        return "🌑 Nouvelle lune"

    if illumination < 25:
        return "🌒 Premier croissant"

    if illumination < 45:
        return "🌓 Premier quartier"

    if illumination < 75:
        return "🌔 Gibbeuse"

    return "🌕 Pleine lune"


def moon_visible_during_window(window_start, window_end, moonrise_time, moonset_time):
   

    if moonrise_time is None and moonset_time is None:
        return False

    if moonrise_time is None:
        return moonset_time >= window_start

    if moonset_time is None:
        return moonrise_time <= window_end

    return moonrise_time <= window_end and moonset_time >= window_start

def safe_moonrise(observer, date, tz):
    try:
        return moonrise(observer, date, tzinfo=tz)
    except ValueError:
        return None


def safe_moonset(observer, date, tz):
    try:
        return moonset(observer, date, tzinfo=tz)
    except ValueError:
        return None

def humidity_penalty(humidity: float) -> float:
    if humidity < 70:
        return 0
    if humidity < 85:
        return 8
    return 18


def precipitation_penalty(precipitation: float) -> float:
    if precipitation <= 0:
        return 0
    if precipitation < 0.1:
        return 3
    if precipitation <0.3:
        return 10
    if precipitation <0.8:
        return 35
    return 80


def wind_penalty(wind: float) -> float:
    if wind < 10:
        return 0
    if wind < 20:
        return 6
    if wind < 30:
        return 14
    return 25


def visibility_penalty(visibility: float | None) -> float:
    if visibility is None:
        return 0

    # Open-Meteo donne souvent la visibilité en mètres.
    
    if visibility > 20000:
        return 0
    if visibility > 10000:
        return 4
    if visibility > 5000:
        return 10
    return 25

def bortle_penalty(bortle: int) -> float:
    penalties = {
        1: 0,
        2: 0,
        3: 0,
        4: 5,
        5: 12,
        6: 25,
        7: 40,
        8: 60,
        9: 80,
    }
    return penalties.get(bortle, 40)

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

def project_progress_bonus(object_name):
    projects = get_projects()

    if object_name not in projects:
        return 0

    project = projects[object_name]
    hours = project.get("hours", 0)
    target_hours = project.get("target_hours", 1)

    if target_hours <= 0:
        return 0

    progress = hours / target_hours

    if progress >= 1:
        return -50

    return round(progress * 20, 1)

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

def estimate_remaining_nights(object_name, avg_night_hours=5):

    remaining = project_remaining_hours(object_name)

    if remaining is None:
        return None

    return max(1, round(remaining / avg_night_hours))


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

    progress_score = (1 - completion) * 50
    remaining_score = min(remaining, 20)

    base_priority = progress_score + remaining_score
    return round(base_priority * (importance / 5), 1)

def altitude_bonus(obj):

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

def project_roi(object_name):
    details = project_details(object_name)

    if not details:
        return 0

    remaining = details["remaining"]

    if remaining <= 0:
        return 0

    importance = details["importance"]

    return round(importance / remaining, 2)

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

def recommend_project():
    projects = get_projects()

    candidates = []

    for name, project in projects.items():
        remaining = project_remaining_hours(name)

        if remaining is None or remaining <= 0:
            continue

        priority = project_priority(name)
        progress = project_progress(name)
        completion_bonus = progress / 5

        season_bonus = altitude_bonus(
            CATALOG.get(name, {})
        )
        season_window = season_window_bonus(CATALOG.get(name, {}))
        roi = project_roi(name)

        portfolio_score = (
            priority * 0.6
            + season_bonus
            + season_window
            + roi * 15
            + completion_bonus
        )

        candidates.append({
            "name": name,
            "remaining": remaining,
            "priority": priority,
            "hours_done": project.get("hours", 0),
            "target_hours": project.get("target_hours", 0),
            "season_bonus": season_bonus,
            "roi": roi,
            "portfolio_score": portfolio_score,
            "season_window": season_window,
            "months_left": season_remaining_months(CATALOG.get(name,{})),
            "progress" : progress,
            "comnpletion_bonus": completion_bonus,
        })


    if not candidates:
        return None
    
    candidates.sort(
        key=lambda x: x["portfolio_score"],
        reverse=True
        )
    
    return candidates[0]

def recommend_project_for_night(top_objects):

    profile = load_user_profile()

    astro_weight = profile["preferences"].get(
        "astro_weight", 0.7
    )

    project_weight = profile["preferences"].get(
        "project_weight", 0.3
    )

    candidates = []

    for obj in top_objects:
        catalog_key = obj.get("catalog_key",obj["name"])

        remaining = project_remaining_hours(catalog_key)

        if remaining is not None and remaining <= 0:
            continue


        astro_score = obj["score"]
        priority = project_priority(catalog_key)
        season_bonus = altitude_bonus(obj)
        roi = project_roi(catalog_key)

        final_score = (
            astro_score * astro_weight
            + priority * project_weight
            + season_bonus
            + roi * 5
        )

        candidates.append({
            "name": obj["name"],
            "astro_score": astro_score,
            "priority": priority,
            "final_score": final_score,
            "season_bonus": season_bonus,
            "roi": roi
        })

        if not candidates:
            return None
        
    candidates.sort(
        key=lambda x: x["final_score"],
        reverse=True
    )

    return candidates


def forecast_available_hours(nights):
    total = 0

    for night in nights:
        window = night.get("best_window")

        if not window:
            continue

        start = int(window["start"].split(":")[0])
        end = int(window["end"].split(":")[0])

        total += end - start

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

    if ranking:
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
        night["top_objects"]
    )

    if not night_projects:
        print("\nAucun projet actif trouvé")
        return

    print("\n===== TOP PROJETS CE SOIR =====")

    for i, project in enumerate(night_projects[:3], start=1):
        print(
            f"{i}. {project['name']} "
            f"(score {project['final_score']:.1f})"
        )

    night_project = night_projects[0]

    obj_key = night_project["name"]
    obj = CATALOG.get(obj_key, {"name": obj_key})

    best_setup = best_equipment_for_object(obj_key)
    best_filters = recommend_filter(obj)

    print(f"Projet : {night_project['name']}")
    print(f"Score astro : {night_project['astro_score']:.1f}")
    print(f"Priorité projet : {night_project['priority']:.1f}")
    print(f"Score final : {night_project['final_score']:.1f}")

    print("\n===== PLAN DE NUIT =====")

    window = night.get("best_window")

    if window:
        print(f"Fenêtre optimale : {window['start']} → {window['end']}")

    print(f"Action recommandée : terminer {night_project['name']}")

    if best_setup:
        print(f"Setup : {best_setup['equipment']}")

    if best_filters:
        print(f"Filtre : {best_filters[0]}")

    show_action_plan(
        night,
        night_project,
        best_setup,
        best_filters
    )

def show_action_plan(
    night,
    night_project,
    best_setup,
    best_filters
):
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
    target_hours = projects[night_project["name"]].get("target_hours", 0)

    future_progress = min(
        100,
        progress + (
            100 * duration / target_hours
        )
    )

    print(
        f"8. Progression après session : "
        f"{future_progress:.1f} %"
    )
    current_hours = projects[night_project["name"]]["hours"]

    remaining_after = max(
    0,
        target_hours - (current_hours + duration)
    )

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

    if total_target > 0:
        portfolio_before = total_done_before / total_target * 100
        portfolio_after = total_done_after / total_target * 100
        portfolio_gain = portfolio_after - portfolio_before

    
        print(
            f"11. Gain portefeuille global : "
            f"+{portfolio_gain:.1f} %"
        )
        next_project = next_project_after(
            night_project["name"]
    )

    if next_project:

        print(
            f"12. Projet suivant recommandé : "
            f"{next_project['name']}"
            )

        print(
            f"    Score : "
            f"{next_project['score']:.1f}"
        )

        print(
            f"    Temps restant : "
            f"{next_project['remaining']:.1f} h"
        )
    
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

    total_remaining = max(0, total_target - total_done)

    global_progress = 0
    if total_target > 0:
        global_progress = round(total_done / total_target * 100, 1)

    print("\n----- TOTAL -----")
    print(f"Heures réalisées : {total_done:.1f} h")
    print(f"Heures restantes : {total_remaining:.1f} h")
    nights = estimate_portfolio_nights()
    print(f"Nuits restantes estimées : {nights}")
    print(f"Progression globale : {global_progress:.1f}%")

def portfolio_score(name):
    priority = project_priority(name)

    obj = CATALOG.get(name, {})

    altitude = altitude_bonus(obj)
    season = season_window_bonus(obj)
    roi = project_roi(name)

    progress = project_progress(name)
    completion = progress / 5

    return (
        priority * 0.6
        + altitude
        + season
        + roi * 15
        + completion
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

        altitude = altitude_bonus(obj)
        season = season_window_bonus(obj)
        roi = project_roi(name)

        progress = project_progress(name)
        completion = progress / 5

        score = (
            priority * 0.6
            + altitude
            + season
            + roi * 15
            + completion
        )

        rows.append({
            "name": name,
            "score": score,
            "priority": priority,
            "progress": progress,
            "remaining": remaining,
            "roi": roi
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
    print(f"Nuits restantes estimées : {total_remaining / 2.0:.1f}")

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


def hour_score(hour, moon_illumination, moon_visible, moon_elevation, moon_target_sep, target_altitude, bortle=4, target="deep_sky", target_object=None, goal="balanced"):
    penalty = 0

    bp = bortle_penalty(bortle)
    cp = cloud_penalty(
    hour["cloud_cover"],
    hour["cloud_cover_low"],
    hour["cloud_cover_mid"],
    hour["cloud_cover_high"]
    )
    
    mp = moon_penalty(moon_illumination, moon_elevation, moon_target_sep)

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
    
    hp = humidity_penalty(hour["relative_humidity_2m"])
    pp = precipitation_penalty(hour["precipitation"])
    wp = wind_penalty(hour["wind_speed_10m"])
    vp = visibility_penalty(hour.get("visibility"))
    tb = temperature_bonus(hour["temperature_2m"])
   
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

    project_bonus = project_progress_bonus(target_object)

    priority_bonus=( 
    project_priority(target_object) * 0.3)

    score = round(
        max(
        0,
        min(
            100,
            45 - penalty + tb + target_bonus + sqm_bonus + project_bonus + priority_bonus
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

def best_windows(hours: list[dict], moon_illumination: float, moon_rise, moon_set, observer, bortle=4, target="deep_sky", target_object="M31", goal="balanced", window_size: int = 2, limit: int = 3):

    if len(hours) < window_size:
        return []
    
    candidates = []

    for i in range(0, len(hours) - window_size + 1):
        window = hours[i:i + window_size]

        visible = moon_visible_during_window(
            window[0]["time"],
            window[-1]["time"] + timedelta(hours=1),
            moon_rise,
            moon_set
        )

        scores = []
        hour_details = []
        moon_impacts = []
        moon_penalties = []

        profile = load_user_profile()
        min_alt = profile.get("preference",{}).get("min_altitude_deg",30)

        for h in window:
            moon_elevation = moon.elevation(
                observer,
                h["time"]
            )

            target_obj = TARGET_OBJECTS[target_object]

            target_alt = target_altitude(
                target_obj["ra"],
                target_obj["dec"],
                h["time"],
                observer.latitude,
                observer.longitude
            )

            profile = load_user_profile()
            min_alt = profile.get("preferences", {}).get("min_altitude_deg", 30)
            if target_alt < min_alt:
                continue

            moon_sep = moon_target_separation(
                target_obj["ra"],
                target_obj["dec"],
                h["time"],
                observer.latitude,
                observer.longitude
            )

            result = hour_score(
                h,
                moon_illumination,
                True,
                moon_elevation,
                moon_sep,
                target_alt,
                bortle,
                target,
                target_object,
                goal=goal
            )

            obj_meta = CATALOG.get(target_object, {})

            difficulty = obj_meta.get("difficulty", 2)
            magnitude = obj_meta.get("magnitude", 8)
            obj_type = obj_meta.get("type", "unknown")

            object_bonus = 0


            target_bonus = 0

            if goal == "nebulae" and obj_type == "nebula":
                target_bonus += 12

            elif goal == "galaxies" and obj_type == "galaxy":
                target_bonus += 12

            ######elif goal == "clusters" and obj_type == "cluster":
                #####target_bonus += 12
            
            ####from astropilot.equipment_profiles import (
                ###CURRENT_EQUIPMENT,
                ##get_fov
            #)
        
            fov = get_fov()

            object_size = obj_meta.get("size_arcmin", 30) / 60
            frame_width = fov["width_deg"]

            frame_diag = (fov["width_deg"]**2 + fov["height_deg"]**2) ** 0.5
            ratio = object_size / frame_diag


            preference_bonus = 0

            if goal == "galaxies" and obj_type == "galaxy":
                preference_bonus = 25

            elif goal == "nebulae" and obj_type in ["nebula", "planetary_nebula"]:
                preference_bonus = 25

            elif goal == "widefield" and object_size >= 1.0:
                preference_bonus = 8

            elif goal == "small_targets" and object_size <= 0.5:
                preference_bonus = 8

            if obj_type in ["planetary_nebula"]:
                ideal_min = 0.02
                ideal_max = 0.20
            elif obj_type in ["galaxy"]:
                ideal_min = 0.05
                ideal_max = 0.40
            elif obj_type in ["cluster"]:
                ideal_min = 0.10
                ideal_max = 0.60
            else:  # nebula
                ideal_min = 0.25
                ideal_max = 0.45

            if ideal_min <= ratio <= ideal_max:
                object_bonus += 20
            elif ratio < ideal_min / 2:
                object_bonus -= 25
            elif ratio < ideal_min:
                object_bonus -= 10
            elif ratio > ideal_max * 1.5:
                object_bonus -= 35
            elif ratio > ideal_max:
                object_bonus -= 15            

            # Bonus difficulté : objets faciles favorisés
            if difficulty == 1:
                object_bonus += 4
            elif difficulty == 2:
                object_bonus += 2
            elif difficulty >= 4:
                object_bonus -= 4

            # Bonus magnitude : objets brillants favorisés
            if magnitude <= 4:
                object_bonus += 4
            elif magnitude <= 7:
                object_bonus += 2
            elif magnitude >= 9:
                object_bonus -= 3

            # Bonus type selon la lune
            if obj_type == "galaxy" and moon_illumination > 50:
                object_bonus -= 5
            elif obj_type in ["nebula", "planetary_nebula"] and moon_illumination > 50:
                object_bonus -= 2
            elif obj_type == "cluster" and moon_illumination > 50:
                object_bonus += 2
                

            result["score"] = max(0, min(100, result["score"] + object_bonus + preference_bonus))

            scores.append(result["score"])
            hour_details.append(result["details"])
            moon_impacts.append(result["moon_impact"])
            moon_penalties.append(result["moon_penalty"])

        if not scores:
            continue

        avg = round(sum(scores) / len(scores))

        avg_alt = sum(
            d["target_altitude"] for d in hour_details
        ) / len(hour_details)

        if avg_alt < 20:
            avg -= 20
        elif avg_alt < 30:
            avg -= 10

        moon_avg = round(
            sum(moon.elevation(observer, h["time"]) for h in window) / len(window),
            1
        )
            
        candidates.append({
                "start": window[0]["time"],
                "end": window[-1]["time"] + timedelta(hours=1),
                "score": avg,
                "hour_scores": scores,
                "details": hour_details,
                "clouds": round(
                    sum(
                        h["cloud_cover_low"] * 0.2 +
                        h["cloud_cover_mid"] * 0.3 +
                        h["cloud_cover_high"] * 0.5
                        for h in window
                    ) / len(window)
                ),
                "humidity": round(
                    sum(h["relative_humidity_2m"] for h in window) / len(window)
                ),
                "wind": round(
                    sum(h["wind_speed_10m"] for h in window) / len(window),
                    1
                ),
                "moon_impact": moon_impacts[0],
                "moon_penalty": round(
                    sum(moon_penalties) / len(moon_penalties),
                    1
                ),
                "moon_elevation": moon_avg,
                "moon_sep": round(
                    sum(d["moon_sep"] for d in hour_details) / len(hour_details),
                    1
                ),
                "target_altitude": round(
                    sum(d["target_altitude"] for d in hour_details) / len(hour_details),
                    1
                ),
                "sqm": round(
                    sum(d["sqm"] for d in hour_details) / len(hour_details),
                    2
                ),
            })
    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:limit]

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
        print("Prévisions météo indisponibles, utilisation météo fallback.")
        rows = fake_clear_weather()
    else:
        rows = parse_hourly_weather(weather)

    results = []
    today = datetime.now(ZoneInfo(TIMEZONE)).date()

    for d in range(7):
        night_date = today + timedelta(days=d)
        current_date = datetime.combine(night_date, datetime.min.time())

        phase = moon_phase(current_date.date())
        illumination = round(moon_illumination_from_phase(phase))

        city_info = LocationInfo(city, "Switzerland", TIMEZONE, lat, lon)

        target_date = current_date.date()

        moon_rise = safe_moonrise(city_info.observer, target_date, ZoneInfo(TIMEZONE))
        moon_set = safe_moonset(city_info.observer, target_date, ZoneInfo(TIMEZONE))

        hours = night_hours_rough(rows, current_date, lat, lon, city)

        if not hours:
            continue

        all_results = []

        for obj_name in TARGET_OBJECTS:
            top_windows = best_windows(
                hours,
                illumination,
                moon_rise,
                moon_set,
                city_info.observer,
                bortle,
                target,
                obj_name,
                goal=goal
            )

            if not top_windows:
                continue

            top_windows.sort(key=lambda x: x["score"], reverse=True)
            best = top_windows[0]

            all_results.append({
                "name": obj_name,
                "score": best["score"],
                "altitude": best.get("target_altitude"),
                "moon_sep": best.get("moon_sep"),
                "sqm": best.get("sqm"),
                "moon_score": best.get("moon_score"),
                "frame_bonus": best.get("frame_bonus"),
                "window": best,
                "catalog_key": obj_name,
            })

        if not all_results:
            continue

        all_results.sort(key=lambda x: x["score"], reverse=True)
        best_score = all_results[0]["score"]

        best_results = [
            r for r in all_results
            if r["score"] == best_score
        ]

        best = best_results[0]["window"]
        best_object = best_results[0]["name"]


        best_setup = best_setup_for_object(best_object)

        if best_setup:
            setup_name = best_setup[0]["equipment"]

            exposure = recommended_exposure(
                CATALOG[best_object],
                bortle=bortle
            )
        else:
            setup_name = "inconnu"
            exposure = "?"

        top3 = all_results[:3]
        top5 = all_results[:5]
        night_score = round(
            sum(r["score"] for r in top3) / len(top3)
        )

        results.append({
            "date": str(night_date),
            "score": night_score,
            "moon_impact": best["moon_impact"],
            "moon_penalty": best["moon_penalty"],
            "best_object_score": all_results[0]["score"],
            "verdict": verdict(night_score),
            "bortle": bortle,
            "object": best_object,
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
                }
                for r in all_results[:5]
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
            "lat": 46.2333,
            "lon": 7.3667,
            "city": "Sion",
            "country": "Switzerland",
        }
    
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


    if args.compare:

        print("Nombre objets :", len(CATALOG))


        for profile in get_available_equipment():
            set_current_equipment(profile)

            fov = get_fov()
            location = get_default_location()

            user_profile = load_user_profile()


            nights = forecast_astro(
                location["latitude"],
                location["longitude"],
                location["name"],
                load_user_profile().get("preferences", {}).get("bortle", 4),
                "deep_sky",
                equipment=None, goal=args.goal
            )

            if nights is None:
                nights = []

            top = sorted(
                    nights,
                    key=lambda x: x["score"],
                    reverse=True
            )[:10]

            for night in top:
                print(
                f'{night["date"]} '
                f'{night["object"]:<18} '
                f'objet={night["best_object_score"]:>3} '
                f'nuit={night["score"]:>3}'
            )

    #exit()

    lat = 46.2333
    lon = 7.3667
    city = "sion"

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

print("\n===== CAPACITÉ À VENIR =====")

for night in top_nights:

    window = night.get("best_window")

    if window:
        start = int(window["start"].split(":")[0])
        end = int(window["end"].split(":")[0])
        duration = end - start
    else:
        duration = 0

    print(f"{night['date']} : {duration:.1f} h")

print(
    f"Total prévisionnel : "
    f"{forecast_available_hours(top_nights):.1f} h"
)


for i, night in enumerate(top_nights, 1):
    print(f"#{i} - {night['date']}")

print("Top objets :")

for j, obj in enumerate(night["top_objects"], start=1):
    print(
        f"{j}. {obj['name']} "
        f"score={obj['score']:.1f} "
        f"alt={obj['altitude']:.0f}° "
        f"moon_sep={obj['moon_sep']:.0f}° "
        f"sqm={obj['sqm']:.1f} "
        f"frame={obj['frame_bonus']} "
        f"project={obj.get('project_bonus', 0)}"
        f"remaining={obj.get('remaining_hours','-')}"
        f"prio={obj.get('priority_bonus',0)}"
)
best_objects = night.get("best_objects") or [night["object"]]
obj_key = best_objects[0]
obj = CATALOG.get(obj_key, {"name": obj_key})

print(f"Objet recommandé : {obj['name']} ({obj_key})")
show_tonight_recommendation(night)
#log_project_session("M31", 2)
#show_project_stats()
show_portfolio_dashboard()
project = recommend_project()
show_portfolio_ranking()
show_completion_forecast()
show_astro_calendar()

if project:
    print("\n===== PROJET RECOMMANDÉ =====\n")
    print(f"Projet : {project['name']}")
    print(
        f"Progression : "
        f"{project['hours_done']} / {project['target_hours']} h")
    print(f"Reste : {project['remaining']:.1f} h")
    print(f"Priorité : {project['priority']:.1f}")
    print(f"Bonus altitude : {project['season_bonus']}")
    print(f"ROI : {project['roi']}")
    print(f"Score portefeuille : {project['portfolio_score']:.1f}")
    print(f"Mois restants : {project['months_left']}")
    print(f"Bonus saison : {project['season_window']}")
    print(f"Progression : {project['progress']} %")
    print(f"Bonus clôture : {project.get('completion_bonus', 0):.1f}")
    #print("\n=== FIN DU PROGRAMME. ===")

    