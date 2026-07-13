from dataclasses import dataclass
from astropy.time import Time
from astropilot.engines.sky_engine import SkyEngine



@dataclass
class SeasonWindow:
    start_date: object
    end_date: object
    peak_date: object
    remaining_days: int | None
    remaining_good_nights: int | None
    urgency: str
    confidence: float


class DynamicSeasonEngine:

    @staticmethod
    def target_altitude_at_time(target, latitude, longitude, obs_time):
        """
        Calcule l'altitude de la cible à une date donnée.
        """

        sky = SkyEngine()

        return sky.target_altitude(
            target["ra"] * 15.0,      # RA en heures -> degrés
            target["dec"],
            Time(obs_time),
            latitude,
            longitude,
        )
    
    @staticmethod
    def target_visibility_window(
        target,
        latitude,
        longitude,
        start_time,
        end_time,
        min_altitude=30,
    ):
        """
        Détermine la fenêtre de visibilité d'une cible.
        """
        from datetime import timedelta

        print("Début fenêtre :", start_time)
        print("Fin fenêtre   :", end_time)

        current = start_time

        samples = []

        while current <= end_time:

            altitude = DynamicSeasonEngine.target_altitude_at_time(
                target,
                latitude,
                longitude,
                current,
            )

            samples.append((current, altitude))

            current += timedelta(minutes=5)

        return samples


    @staticmethod
    def summary(context):
        """
        Version dynamique.
        Pour l'instant on renvoie simplement None.
        Elle sera construite progressivement.
        """
        return None
    
    
