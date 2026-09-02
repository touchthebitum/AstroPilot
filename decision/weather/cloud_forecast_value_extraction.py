from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherValue,
    WeatherVariable,
)


def extract_cloud_forecast_value(
    forecast_point: WeatherForecastPoint,
) -> WeatherValue | None:
    for value in forecast_point.values:
        if value.variable is WeatherVariable.CLOUD_COVER_PERCENT:
            return value
    return None
