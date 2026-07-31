from __future__ import annotations

from collections.abc import Callable

class ForecastEngine:

    def __init__(
        self,
        *,
        fetch_weather: Callable[[float, float], dict | None],
        parse_hourly_weather: Callable[[dict], list[dict]],
    ):
        self.fetch_weather = fetch_weather
        self.parse_hourly_weather = parse_hourly_weather

    def prepare_weather(
        self,
        lat: float,
        lon: float,
        weather: dict | None = None,
    ) -> list[dict] | None:
        if weather is None:
            try:
                weather = self.fetch_weather(lat, lon)
            except Exception as exc:
                print("ERREUR fetch_weather =", repr(exc))
                weather = None

        if weather is None:
            print("ERREUR : prévisions météo indisponibles.")
            print("Recommandation météo réelle impossible.")
            return None

        return self.parse_hourly_weather(weather)

    def forecast_astro(
        self,
        lat,
        lon,
        city,
        bortle,
        target="deep_sky",
        equipment=None,
        goal="nebulae",
        weather=None,
    ):
        raise NotImplementedError