import math
from datetime import timedelta
from astral import moon
from astral.moon import moonrise, moonset
from astral.sun import sun
from astral import moon
from astropilot.user_profile import load_user_profile
from astropy.coordinates import SkyCoord, get_body, EarthLocation, AltAz
from astropy.time import Time
from astropy.utils import iers
iers.conf.auto_download = False
iers.conf.auto_max_age = None

import astropy.units as u
class SkyEngine:
    """
    Analyse uniquement le ciel.

    Responsabilités :
    - météo
    - Lune
    - humidité
    - vent
    - visibilité
    - qualité astronomique
    - fenêtres utiles

    Ne connaît pas :
    - portefeuille
    - ROI
    - setup
    - utilisateur
    - stratégie projet
    """

    def __init__(self, context=None):
        self.context = context or {}

    def sky_quality(self):
        """
        Retourne une qualité de ciel simple.
        Version initiale volontairement minimale.
        """
        return {
            "score": None,
            "reasons": [],
            "warnings": []
        }

    def moon_phase_name(self,illumination):

        if illumination < 5:
            return "🌑 Nouvelle lune"

        if illumination < 25:
            return "🌒 Premier croissant"

        if illumination < 45:
            return "🌓 Premier quartier"

        if illumination < 75:
            return "🌔 Gibbeuse"

        return "🌕 Pleine lune"
    
    def moon_illumination_from_phase(self, phase: float) -> float:
        """
        Astral renvoie une phase entre 0 et environ 29.5 jours.
        0 = nouvelle lune
        14-15 = pleine lune
        """

        normalized = phase / 29.53
        illum = (1 - math.cos(2 * math.pi * normalized)) / 2

        return illum * 100
    
    def moon_visible_during_window(self, window_start, window_end, moonrise_time, moonset_time):
        from datetime import datetime

        if not isinstance(moonrise_time, datetime):
            moonrise_time = None

        if not isinstance(moonset_time, datetime):
            moonset_time = None

        if moonrise_time is None and moonset_time is None:
            return False

        if moonrise_time is None:
            return moonset_time >= window_start

        if moonset_time is None:
            return moonrise_time <= window_end

        return moonrise_time <= window_end and moonset_time >= window_start
    
    def safe_moonrise(self, observer, date, tz):
        try:
            return moonrise(observer=observer, date=date, tzinfo=tz)
        except ValueError:
            return None
        
    def safe_moonset(self,observer, date, tz):
        try:
            return moonset(observer=observer, date=date, tzinfo=tz)
        except ValueError:
            return None
        
    def moon_target_separation(self, target_ra, target_dec, obs_time, lat, lon):
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
    
    def target_altitude(self, target_ra, target_dec, obs_time, lat, lon):

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
    
    def target_altitude_bonus(self, alt):
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
        

    def cloud_penalty(self, total, low, mid, high):

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


    def temperature_bonus(self, temp):

        if 8 <= temp <= 18:
            return 5

        if 0 <= temp < 8:
            return 2

        if temp > 18:
            return 2

        return 0
    
    def moon_penalty(self, illumination, moon_elevation, moon_sep):

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
    
    def humidity_penalty(self, humidity: float) -> float:
        if humidity < 70:
            return 0
        if humidity < 85:
            return 8
        return 18
    
    def precipitation_penalty(self,precipitation: float) -> float:
        if precipitation <= 0:
            return 0
        if precipitation < 0.1:
            return 3
        if precipitation <0.3:
            return 10
        if precipitation <0.8:
            return 35
        return 80


    def wind_penalty(self,wind: float) -> float:
        if wind < 10:
            return 0
        if wind < 20:
            return 6
        if wind < 30:
            return 14
        return 25


    def visibility_penalty(self,visibility: float | None) -> float:
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

    def bortle_penalty(self,bortle: int) -> float:
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
    
    
        
    def cloud_score(self):
        pass

    def moon_score(self):
        pass

    def weather_score(self):
        pass

    def bortle_score(self):
        pass

    def sqm_score(self):
        pass

    def estimated_sqm(
        self,
        bortle,
        moon_illumination,
        moon_elevation,
        moon_target_sep,
    ):
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
    

    def hour_geometry(
        self,
        hour,
        observer,
        target_obj,
        lat,
        lon,
    ):
        moon_elevation = moon.elevation(
            observer,
            hour["time"]
        )

        target_alt = self.target_altitude(
            target_obj["ra"],
            target_obj["dec"],
            hour["time"],
            observer.latitude,
            observer.longitude
        )

        moon_sep = self.moon_target_separation(
            target_obj["ra"],
            target_obj["dec"],
            hour["time"],
            lat,
            lon
        )

        return {
            "moon_elevation": moon_elevation,
            "target_altitude": target_alt,
            "moon_target_sep": moon_sep,
        }

    
    def score_hour(self, hour,moon_illumination,observer,lat,lon,target_obj,bortle,target,goal,):

        geometry = self.hour_geometry(
            hour,
            observer,
            target_obj,
            lat,
            lon,
        )

        moon_elevation = geometry["moon_elevation"]
        target_altitude = geometry["target_altitude"]
        moon_target_sep = geometry["moon_target_sep"]
        
        
        bp = self.bortle_penalty(bortle)

        cp = self.cloud_penalty(
            hour["cloud_cover"],
            hour["cloud_cover_low"],
            hour["cloud_cover_mid"],
            hour["cloud_cover_high"],
        )

        mp = self.moon_penalty(
            moon_illumination,
            moon_elevation,
            moon_target_sep,
        )

        hp = self.humidity_penalty(
            hour["relative_humidity_2m"]
        )

        wp = self.wind_penalty(
            hour["wind_speed_10m"]
        )

        vp = self.visibility_penalty(
            hour.get("visibility")
        )

        pp = self.precipitation_penalty(
            hour["precipitation"]
        )

        tb = self.temperature_bonus(
            hour["temperature_2m"]
        )

        ab = self.target_altitude_bonus(
            target_altitude
        )

        sqm = self.estimated_sqm(
            bortle,
            moon_illumination,
            moon_elevation,
            moon_target_sep,
        )

        score = 100 - bp - cp - mp - hp - wp - vp - pp + tb + ab
        score = max(0, min(100, score))
        
        return {
            "score": score,
            "moon_impact": mp,
            "moon_penalty": mp,
            "target_altitude": target_altitude,
            "moon_elevation": moon_elevation,
            "moon_target": moon_target_sep,

            "details": {
                "bortle": bp,
                "cloud": cp,
                "moon": mp,
                "humidity": hp,
                "wind": wp,
                "visibility": vp,
                "precipitation": pp,
                "temperature_bonus": tb,
                "altitude_bonus": ab,
                "target_altitude": target_altitude,
                "moon_sep": moon_target_sep,
                "moon_target_sep": moon_target_sep,
                "frame_bonus": 0,
                "sqm": sqm,
            },

            "bp": bp,
            "cp": cp,
            "mp": mp,
            "hp": hp,
            "wp": wp,
            "vp": vp,
            "pp": pp,
            "tb": tb,
            "ab": ab,
            "sqm": sqm,
                
            }
    
    def best_windows(self,hours, moon_illumination, moon_rise, moon_set, observer, lat, lon,bortle=4, target="deep_sky", target_object="M31",target_obj=None, goal="balanced", window_size= 2,min_altitude_deg=30, limit= 3):

        if target_obj is None:
            raise ValueError("target_obj is required")
        
        profile = load_user_profile()

        if window_size is None:
            window_size = profile.get("preferences", {}).get("window_size", 2)

        sky = self

        windows = self.iter_windows(hours, window_size)

        if not windows:
            return []

        candidates = []

        for window in windows:

            visible = sky.moon_visible_during_window(
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

            min_alt = profile.get("preferences",{}).get("min_altitude_deg",30)

            for h in window:
                #target_obj = TARGET_OBJECTS[target_object]

                geometry = self.hour_geometry(
                    h,
                    observer,
                    target_obj,
                    lat,
                    lon
                )

                moon_elevation = geometry["moon_elevation"]
                target_alt = geometry["target_altitude"]
                moon_sep = geometry["moon_target_sep"]
                if target_alt < min_alt:
                    continue

                result = self.score_hour(
                    h,
                    moon_illumination,
                    observer,
                    lat,
                    lon,
                    target_obj,
                    bortle,
                    target,
                    goal,
                )
                
                seeing = self.estimate_seeing(
                    h.get("wind_speed_10m", 0),
                    h.get("relative_humidity_2m", 0),
                )
                

                obj_meta = target_obj or {}

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
            
                frame_bonus = 0

                object_size = obj_meta.get("size_arcmin", 30) / 60
                ratio = 1

                ####object_size = obj_meta.get("size_arcmin", 30) / 60
                ###frame_width = fov["width_deg"]

                ##frame_diag = (fov["width_deg"]**2 + fov["height_deg"]**2) ** 0.5
                #ratio = object_size / frame_diag


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

            avg_humidity = round(
                sum(h["relative_humidity_2m"] for h in window) / len(window),
                1
            )

            avg_wind = round(
                sum(h["wind_speed_10m"] for h in window) / len(window),
                1
            )

            seeing = self.estimate_seeing(
                avg_wind,
                avg_humidity,
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

                    "visibility": round(
                        sum(h["visibility"] for h in window) / len(window),
                        1
                    ),

                    "seeing" : seeing,
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

                
    def iter_windows(self, hours, window_size):
        if len(hours) < window_size:
            return []

        windows = []

        for i in range(0, len(hours) - window_size + 1):
            windows.append(hours[i:i + window_size])

        return windows
    
    def estimate_seeing(self, wind, humidity):
        """
        Estimation simple du seeing (arcsec).
        Plus la valeur est basse, meilleur est le seeing.
        """

        seeing = 1.5

        # Vent
        if wind > 20:
            seeing += 1.0
        elif wind > 10:
            seeing += 0.5

        # Humidité
        if humidity > 90:
            seeing += 0.8
        elif humidity > 80:
            seeing += 0.4

        return round(seeing, 1)
        
    