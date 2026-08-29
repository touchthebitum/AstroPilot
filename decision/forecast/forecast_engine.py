from __future__ import annotations
from collections.abc import Callable
from decision.weather.weather_forecast import WeatherForecast
from datetime import datetime
from zoneinfo import ZoneInfo
from astral import LocationInfo
from astropilot.engines.sky_engine import SkyEngine
from decision.forecast.night_evaluation import NightEvaluation

class ForecastEngine:

    def __init__(
        self,
        *,
        fetch_weather: Callable[[float, float], dict | None],
        parse_hourly_weather: Callable[[dict], list[dict]],
        evaluate_object,
        target_objects,
        moon_phase,
        night_hours_rough,
        timezone,
        decision_engine_factory,
        altitude_rule_factory,
    ):
        self.fetch_weather = fetch_weather
        self.parse_hourly_weather = parse_hourly_weather
        self.evaluate_object = evaluate_object
        self.target_objects = target_objects
        self.moon_phase = moon_phase
        self.night_hours_rough = night_hours_rough
        self.timezone = timezone
        self.decision_engine_factory = decision_engine_factory
        self.altitude_rule_factory = altitude_rule_factory

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

    def build_weather_forecast(
        self,
        rows: list[dict],
    ) -> WeatherForecast:
        return WeatherForecast(
            hourly=rows,
            hourly_clouds=[
                hour.get("cloud_cover", 100)
                for hour in rows
            ],
            hourly_humidity=[
                hour.get("relative_humidity_2m", 100)
                for hour in rows
            ],
            hourly_wind=[
                hour.get("wind_speed_10m", 0)
                for hour in rows
            ],
            hourly_temperature=[
                hour.get("temperature_2m", 0)
                for hour in rows
            ],
            hourly_visibility=[
                hour.get("visibility", 10000)
                for hour in rows
            ],
        )

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

    def evaluate_night(
        self,
        *,
        all_results,
    ):
        if not all_results:
            return None

        all_results.sort(
            key=lambda result: result["global_score"],
            reverse=True,
        )

        best_score = all_results[0]["global_score"]
        top3 = all_results[:3]

        best_object = top3[0]["name"]
        best = top3[0]["window"]
        setup_name = top3[0].get(
            "best_setup",
            "inconnu",
        )

        night_score = round(
            sum(
                result["global_score"]
                for result in top3
            ) / len(top3)
        )

        return NightEvaluation(
            all_results=all_results,
            top3=top3,
            best_score=best_score,
            best_object=best_object,
            best=best,
            setup_name=setup_name,
            night_score=night_score,
        )

    def forecast_one_night(
        self,
        *,
        night_date,
        rows,
        lat,
        lon,
        city,
        bortle,
        target,
        profile,
    ):
        row_zone = (
            rows[0].get("time").tzinfo
            if rows
            and isinstance(rows[0], dict)
            and getattr(rows[0].get("time"), "tzinfo", None) is not None
            else None
        )
        timezone_name = getattr(row_zone, "key", self.timezone)
        current_date = datetime.combine(
            night_date,
            datetime.min.time(),
        )

        phase = self.moon_phase(current_date.date())

        sky = SkyEngine()

        illumination = round(
            sky.moon_illumination_from_phase(phase)
        )

        city_info = LocationInfo(
            city,
            "",
            timezone_name,
            lat,
            lon,
        )

        target_date = current_date.date()

        moon_rise = sky.safe_moonrise(
            city_info.observer,
            target_date,
            ZoneInfo(timezone_name),
        )

        moon_set = sky.safe_moonset(
            city_info.observer,
            target_date,
            ZoneInfo(timezone_name),
        )

        hours = self.night_hours_rough(
            rows,
            current_date,
            lat,
            lon,
            city,
        )

        if not hours:
            return None

        decision_engine = self.decision_engine_factory()
        decision_engine.add_rule(
            self.altitude_rule_factory()
        )

        weather_forecast = self.build_weather_forecast(rows)

        all_results = self.evaluate_targets(
            sky=sky,
            hours=hours,
            weather=weather_forecast,
            illumination=illumination,
            moon_rise=moon_rise,
            moon_set=moon_set,
            city_info=city_info,
            lat=lat,
            lon=lon,
            bortle=bortle,
            target=target,
            profile=profile,
            decision_engine=decision_engine,
        )

        night_evaluation = self.evaluate_night(
            all_results=all_results,
        )

        if night_evaluation is None:
            return None

        return {
            "current_date": current_date,
            "sky": sky,
            "illumination": illumination,
            "city_info": city_info,
            "moon_rise": moon_rise,
            "moon_set": moon_set,
            "hours": hours,
            "evaluation": night_evaluation,
        }
