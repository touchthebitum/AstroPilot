from __future__ import annotations
import math
from decision.models.future_opportunity import FutureOpportunity
from decision.intelligence.analysis_context import AnalysisContext
from decision.season.season_resolver import SeasonResolver


class FutureOpportunityEngine:
    """
    Analyse les opportunités futures d'un projet
    et estime le risque de report.
    """

    def __init__(
        self,
        catalog,
        weather_provider,
        season_engine,
        profile_provider,
        project_provider,
    ):
        self.catalog = catalog
        self.weather_provider = weather_provider
        self.season_engine = season_engine
        self.profile_provider = profile_provider
        self.project_provider = project_provider

    def estimate(
        self,
        project_name: str,
        remaining_hours: float | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        observation_time=None,
    ) -> FutureOpportunity:
        project = self.catalog.get(project_name)

        if not project:
            return FutureOpportunity(
                good_nights=0,
                risk="INCONNU",
                weather_ratio=0.0,
                needed_nights=0,
                opportunity_ratio=0.0,
            )

        project = project.copy()
        project["catalog_key"] = project_name

        profile = self.profile_provider()
        location = profile.get("location", {})

        lat = (
            latitude
            if latitude is not None
            else location.get("latitude")
        )
        lon = (
            longitude
            if longitude is not None
            else location.get("longitude")
        )

        if (
            latitude is not None
            and longitude is not None
            and observation_time is not None
        ):
            season = SeasonResolver.resolve(
                AnalysisContext(
                    target=project_name,
                    latitude=latitude,
                    longitude=longitude,
                    observation_time=observation_time,
                )
            )
            season_days = season["remaining_days"]
            season_good_nights = season["remaining_good_nights"]
        else:
            season_days = self.season_engine(project)
            season_good_nights = None

        if season_days is None:
            return FutureOpportunity(
                good_nights=0,
                risk="INCONNU",
                weather_ratio=0.0,
                needed_nights=0,
                opportunity_ratio=0.0,
            )

        weather_ratio = 0.35

        if lat is not None and lon is not None:
            weather = self.weather_provider(lat, lon)

            if weather:
                weather_ratio = self._estimate_weather_good_night_ratio(weather)

        if season_good_nights is not None:
            good_nights = int(
                season_good_nights * weather_ratio
            )
        else:
            good_nights = max(
                1,
                int(season_days * weather_ratio),
            )

        if remaining_hours is None:
            remaining = self.project_provider(project_name)
        else:
            remaining = remaining_hours

        if remaining is None:
            remaining = 10

        needed_nights = max(
            1,
            math.ceil(remaining / 3),
        )

        opportunity_ratio = round(
            good_nights / needed_nights,
            1,
        )

        if good_nights == 0:
            risk = "CRITIQUE"
        elif good_nights <= 2:
            risk = "ÉLEVÉ"
        elif opportunity_ratio > 5:
            risk = "FAIBLE"
        else:
            risk = "MOYEN"

        return FutureOpportunity(
            good_nights=good_nights,
            risk=risk,
            weather_ratio=weather_ratio,
            needed_nights=needed_nights,
            opportunity_ratio=opportunity_ratio,
        )

    @staticmethod
    def _estimate_weather_good_night_ratio(weather) -> float:
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

        for i, timestamp in enumerate(times):
            hour = int(timestamp[11:13])

            if 4 < hour < 22:
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

        return good_hours / total_night_hours
