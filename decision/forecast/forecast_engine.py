from __future__ import annotations

from collections.abc import Callable

class ForecastEngine:

    def __init__(
        self,
        *,
        fetch_weather: Callable[[float, float], dict | None],
        parse_hourly_weather: Callable[[dict], list[dict]],
        evaluate_object,
        target_objects,
    ):
        self.fetch_weather = fetch_weather
        self.parse_hourly_weather = parse_hourly_weather
        self.evaluate_object = evaluate_object
        self.target_objects = target_objects

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

    def evaluate_targets(
        self,
        *,
        sky,
        hours,
        weather,
        illumination,
        moon_rise,
        moon_set,
        city_info,
        lat,
        lon,
        bortle,
        target,
        profile,
        decision_engine,
    ):
        all_results = []

        for obj_name in self.target_objects:
            result = self.evaluate_object(
                obj_name=obj_name,
                sky=sky,
                hours=hours,
                weather=weather,
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

        return all_results

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