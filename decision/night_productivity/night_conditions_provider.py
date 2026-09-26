from datetime import datetime, timedelta

from decision.season.dynamic_season_engine import DynamicSeasonEngine
from decision.time_math import add_elapsed_time


class NightConditionsProvider:

    @staticmethod
    def _hour_index(hour):
        return int(hour)

    @staticmethod
    def _value(hour, values, fallback):
        if not values:
            return fallback

        index = NightConditionsProvider._hour_index(hour)

        if index < 0:
            return fallback

        if index >= len(values):
            return values[-1]

        return values[index]

    @staticmethod
    def cloud(hour, context):
        if context.weather and context.weather.hourly_clouds:
            return NightConditionsProvider._value(
                hour,
                context.weather.hourly_clouds,
                context.cloud_cover,
            )

        return context.cloud_cover

    @staticmethod
    def humidity(hour, context):
        if context.weather and context.weather.hourly_humidity:
            return NightConditionsProvider._value(
                hour,
                context.weather.hourly_humidity,
                context.humidity,
            )

        return context.humidity

    @staticmethod
    def wind(hour, context):
        if context.weather and context.weather.hourly_wind:
            return NightConditionsProvider._value(
                hour,
                context.weather.hourly_wind,
                context.wind,
            )

        return context.wind

    @staticmethod
    def seeing(hour, context):
        return NightConditionsProvider._value(
            hour,
            context.hourly_seeing,
            context.seeing,
        )

    @staticmethod
    def moon_penalty(hour, context):
        return NightConditionsProvider._value(
            hour,
            context.hourly_moon_penalty,
            context.moon_penalty,
        )

    @staticmethod
    def altitude(hour, context):

        obs_time = add_elapsed_time(
            context.observation_time,
            timedelta(hours=hour),
        )

        return DynamicSeasonEngine.target_altitude_at_time(
            target=context.target,
            latitude=context.latitude,
            longitude=context.longitude,
            obs_time=obs_time,
        )
