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
        "size_arcmin": value["size_arcmin"],
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
    equipment = EQUIPMENT_PROFILES[CURRENT_EQUIPMENT]

    sensor_width = equipment["sensor_width_mm"]
    focal = equipment["focal_length_mm"]

    fov_deg = 57.3 * sensor_width / focal

    object_deg = CATALOG[target_object]["size_arcmin"] / 60
    
    ratio = object_deg / fov_deg


    if 0.25 <= ratio <= 0.8:
        return 10

    elif 0.15 <= ratio < 0.25:
        return 5

    elif 0.1 < ratio <= 0.15:
        return 0
    
    elif 0.8 < ratio <= 1.0:
        return 0
    
    elif 1.0 < ratio <= 1.2:
        return -10
    
    elif ratio > 1.2:
        return -20
    else:
         return -5

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
        response = requests.get(url, params=params, timeout=60)
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
    import math
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

def hour_score(hour, moon_illumination, moon_visible, moon_elevation, moon_target_sep, target_altitude, bortle=4, target="deep_sky", target_object=None):
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
    moon_target_sep
)
    
    target_bonus = 0

    if target_altitude > 80:
        target_bonus = 10
    elif target_altitude > 70:
        target_bonus = 7
    elif target_altitude > 60:
        target_bonus = 4
    elif target_altitude > 45:
        target_bonus = 2
    elif target_altitude > 30:
        target_bonus = -0
    elif target_altitude > 20:
        target_bonus = -5
    else:
        target_bonus = -15
          
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
        
    frame_bonus = framing_bonus(target_object)if target_object else 0
    
    score = round(
    max(
        0,
        min(
            100,
            75 - penalty + tb + target_bonus + sqm_bonus + frame_bonus
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

    return [r for r in rows if start <= r["time"] <= end]

    for r in night_rows:
        print(r["time"])

    return night_rows
    return [r for r in rows if start <= r["time"] <= end]


def best_windows(hours: list[dict], moon_illumination: float, moon_rise, moon_set, observer, bortle=4, target="deep_sky", target_object="M31", window_size: int = 2, limit: int = 3):
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

        for h in window:
            moon_elevation = moon.elevation(
                observer,
                h["time"]
            )

            target_obj = TARGET_OBJECTS[target_object]
            equipment = EQUIPMENT_PROFILES[CURRENT_EQUIPMENT]

            target_alt = target_altitude(
                target_obj["ra"],
                target_obj["dec"],
                h["time"],
                observer.latitude,
                observer.longitude
            )

            if target_alt < 15:
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
                visible,
                moon_elevation,
                moon_sep,
                target_alt,
                bortle,
                target,
                target_object
            )

            obj_meta = CATALOG.get(target_object, {})

            difficulty = obj_meta.get("difficulty", 2)
            magnitude = obj_meta.get("magnitude", 8)
            obj_type = obj_meta.get("type", "unknown")

            object_bonus = 0

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


            #print(
                #target_object,
                #"base=", result["score"],
                #"bonus=", object_bonus,
                #"final=", result["score"] + object_bonus
#)

            #if target_object in ["IC1396", "NorthAmerica", "M13", "M101"]:
                #print(
                    #target_object,
                    #"base=", result["score"],
                    #"bonus=", object_bonus,
                    #"final=", result["score"] + object_bonus
    #)

            result["score"] = max(0, min(100, result["score"] + object_bonus))

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

def forecast_astro(lat: float, lon: float, name: str = "Lieu choisi", bortle: int = 4, target="deep_sky"):
    weather = fetch_weather(lat, lon)

    if weather is None:
        print("Prévisions météo indisponibles.")
        return []

    rows = parse_hourly_weather(weather)

    results = []
    today = datetime.now(ZoneInfo(TIMEZONE)).date()

    for d in range(7):
        night_date = today + timedelta(days=d)

        current_date = datetime.combine(
            night_date,
            datetime.min.time()
        )

        phase = moon_phase(current_date.date())
        illumination = round(moon_illumination_from_phase(phase))

        city = LocationInfo(
            name,
            "Switzerland",
            TIMEZONE,
            lat,
            lon
        )

        target_date = current_date.date()

        moon_rise = safe_moonrise(
            city.observer,
            target_date,
            ZoneInfo(TIMEZONE)
        )

        moon_set = safe_moonset(
            city.observer,
            target_date,
            ZoneInfo(TIMEZONE)
        )

        hours = night_hours_rough(rows, current_date, lat, lon, name)

        if not hours:
            continue

        all_results = []

        for obj_name in TARGET_OBJECTS:
            top_windows = best_windows(
                hours,
                illumination,
                moon_rise,
                moon_set,
                city.observer,
                bortle,
                target,
                obj_name
            )

            if not top_windows:
                continue

            best = top_windows[0]
                
            all_results.append({
                "object": obj_name,
                "score": best["score"],
                "window": best
            })

            print("\nClassement objets :")

            for r in sorted(all_results,
                key=lambda x: x["score"],
                reverse=True):

                w = r["window"]

                print(
                    f"{r['object']:12s}"
                    f" score={r['score']:3d}"
                    f" alt={w['target_altitude']:4.1f}"
                    f" moon={w['moon_sep']:5.1f}"
                    f" sqm={w['sqm']:4.2f}"
            )

            print("\nTop 10 objets :")

            for r in all_results[:10]:

                obj = CATALOG[r["object"]]
                w = r["window"]

                print(
                    f"{r['object']:10s}"
                    f"{obj['name']:30s}"
                    f" score={r['score']:3d}"
                    f" alt={w['target_altitude']:4.1f}"
                    f" moon={w['moon_sep']:5.1f}"
                    f" sqm={w['sqm']:4.2f}"
        )
        if len(all_results) == 0:
            continue

        all_results.sort(
        key=lambda x: x["score"],
        reverse=True
        )

        best = all_results[0]["window"]
        best_object = all_results[0]["object"]

        night_score = round(
            sum(r["score"] for r in all_results[:3]) / len(all_results[:3])
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
            "top_objects": [
                {
                    "name": r["object"],
                    "score": int(r["score"]),
                    "altitude": round(float(r["window"]["target_altitude"]), 1),
                    "moon_sep": round(float(r["window"]["moon_sep"]), 1),
                    "sqm": round(float(r["window"]["sqm"]), 2),
                    "moon_score": round(float(r["window"]["details"][0]["moon"]), 1),
                    "frame_bonus": round(float(r["window"]["details"][0]["frame_bonus"]), 1),
                
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

    return sorted(results, key=lambda x: x["score"], reverse=True)
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

if __name__ == "__main__":

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
        nights = forecast_astro(lat, lon, city, bortle, TARGET)

    top_nights = sorted(
    nights,
    key=lambda x: x["score"],
    reverse=True
    )[:3]

    for night in top_nights:
   
        print("\n======================")
        print("Date :", night["date"])
        print("Score :", night["score"], "/100")
        print("Verdict :", night["verdict"])
        print("Bortle :", night["bortle"])

        print(
        "Meilleur créneau :",
        night["best_window"]["start"],
        "-",
        night["best_window"]["end"]
    )
    
        print(
        "Score créneau :",
        night["best_window"]["score"],
        "/100"
    )
        print(
        "Lune :",
        night["moon"]["illumination"],
        "%"
    )
        
        print("Impact lune :", night["moon_impact"], f"({night['moon_penalty']}/100)")
        
        night["moon_impact"],
        f"({night['moon_penalty']}/100)"
       
        
        print(
        "Nuages :",
        night["weather_summary"]["cloud_cover_percent"],
        "%"
    )
        print("Altitude lune :", round(night["top_windows"][0]["moon_elevation"], 1), "°")
        print("Distance lune-cible :", round(night["top_windows"][0]["moon_sep"], 1), "°")
        print("Distance lune-cible :",night["top_windows"][0]["moon_sep"],"°")
        print(
    "Altitude cible :",
    night["top_windows"][0]["target_altitude"],
    "°"
    ) 
        print(
        "Humidité :",
        night["weather_summary"]["humidity_percent"],
        "%"
    )
        print(
    "Lever lune :",
    night["moon"]["rise"]
    )

        print(
    "Coucher lune :",
    night["moon"]["set"]
    )
        print(
        "Vent :",
        night["weather_summary"]["wind_kmh"],
        "km/h"
        
    )

            
    top_nights = sorted(nights, key=lambda x: x["score"], reverse=True)[:3]
    

        
    for i, night in enumerate(top_nights, 1):
                    print(f"#{i} — {night['date']}")
                    obj_key = night["object"]
                    obj = CATALOG.get(obj_key, {"name": obj_key})

                    print(
                        f"Objet recommandé : "
                        f"{obj['name']} ({obj_key})"
                    )
                    print(f"Score objet      : {night['best_object_score']}/100")
                    print(f"Score nuit       : {night['score']}/100")
                    print(f"SQM              : {night['top_windows'][0]['sqm']:.2f}")
                    print(
                        f"Fenêtre optimale : "
                        f"{night['best_window']['start']} → {night['best_window']['end']}"
                    )

                    

    print()
   
 
        
        

