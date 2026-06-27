import math
from astral import moon
from astral.moon import moonrise, moonset
from astral.sun import sun
from astral import moon
from astropy.coordinates import SkyCoord, get_body, EarthLocation, AltAz
from astropy.time import Time
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

    
    def score_hour(self, hour,moon_illumination,moon_elevation,moon_target_sep, target_altitude, bortle,):

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

        return {
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
    def iter_windows(self, hours, window_size):
        if len(hours) < window_size:
            return []

        windows = []

        for i in range(0, len(hours) - window_size + 1):
            windows.append(hours[i:i + window_size])

        return windows
                