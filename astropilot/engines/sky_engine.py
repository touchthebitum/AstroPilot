import math
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