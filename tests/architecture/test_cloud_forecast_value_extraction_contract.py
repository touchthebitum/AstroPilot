from datetime import datetime, timedelta, timezone

from decision.weather.cloud_forecast_value_extraction import (
    extract_cloud_forecast_value,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


RETRIEVED_AT = datetime(2026, 9, 1, 18, tzinfo=timezone.utc)
LOCATION = WeatherLocation(46.7508, 6.5495)


def forecast_point(*values):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=RETRIEVED_AT + timedelta(hours=1),
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=values,
    )


def test_extracts_exact_cloud_value_from_cloud_only_point():
    cloud = WeatherValue(
        variable=WeatherVariable.CLOUD_COVER_PERCENT,
        value=42.0,
        unit="%",
    )

    assert extract_cloud_forecast_value(forecast_point(cloud)) is cloud


def test_extracts_exact_cloud_value_when_not_first():
    temperature = WeatherValue(
        variable=WeatherVariable.TEMPERATURE_C,
        value=8.0,
        unit="°C",
    )
    cloud = WeatherValue(
        variable=WeatherVariable.CLOUD_COVER_PERCENT,
        value=75.0,
        unit="%",
    )

    assert (
        extract_cloud_forecast_value(forecast_point(temperature, cloud))
        is cloud
    )


def test_returns_none_when_cloud_value_is_absent():
    temperature = WeatherValue(
        variable=WeatherVariable.TEMPERATURE_C,
        value=8.0,
        unit="°C",
    )

    assert extract_cloud_forecast_value(forecast_point(temperature)) is None
