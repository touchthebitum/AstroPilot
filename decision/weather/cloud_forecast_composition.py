from decision.field_observation import CloudCondition
from decision.weather.cloud_forecast_comparison import (
    CloudForecastComparison,
    compare_cloud_conditions,
)
from decision.weather.cloud_mapping_policy import map_cloud_cover_to_condition
from decision.weather.provider_reliability import WeatherValue, WeatherVariable


def compose_cloud_forecast_comparison(
    forecast_value: WeatherValue,
    observed_condition: CloudCondition,
) -> CloudForecastComparison:
    if forecast_value.variable is not WeatherVariable.CLOUD_COVER_PERCENT:
        raise ValueError("invalid_cloud_forecast_value")

    forecast_condition = map_cloud_cover_to_condition(forecast_value.value)
    return compare_cloud_conditions(
        forecast_condition,
        observed_condition,
    )
