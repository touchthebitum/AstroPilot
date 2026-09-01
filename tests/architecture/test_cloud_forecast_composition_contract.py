import pytest

from decision.field_observation import CloudCondition
from decision.weather.cloud_forecast_comparison import CloudForecastComparison
from decision.weather.cloud_forecast_composition import (
    compose_cloud_forecast_comparison,
)
from decision.weather.provider_reliability import WeatherValue, WeatherVariable


@pytest.mark.parametrize(
    (
        "cloud_cover_percent",
        "observed_condition",
        "expected_forecast_condition",
    ),
    [
        (0.0, CloudCondition.OVERCAST, CloudCondition.CLEAR),
        (24.999, CloudCondition.CLEAR, CloudCondition.FEW),
        (25.0, CloudCondition.FEW, CloudCondition.PARTLY_CLOUDY),
        (80.0, CloudCondition.PARTLY_CLOUDY, CloudCondition.OVERCAST),
        (100.0, CloudCondition.MOSTLY_CLOUDY, CloudCondition.OVERCAST),
    ],
)
def test_composes_cloud_forecast_value_with_observed_condition(
    cloud_cover_percent,
    observed_condition,
    expected_forecast_condition,
):
    forecast_value = WeatherValue(
        variable=WeatherVariable.CLOUD_COVER_PERCENT,
        value=cloud_cover_percent,
        unit="%",
    )

    comparison = compose_cloud_forecast_comparison(
        forecast_value,
        observed_condition,
    )

    assert isinstance(comparison, CloudForecastComparison)
    assert comparison.forecast_condition is expected_forecast_condition
    assert comparison.observed_condition is observed_condition


def test_rejects_non_cloud_forecast_value():
    forecast_value = WeatherValue(
        variable=WeatherVariable.TEMPERATURE_C,
        value=10.0,
        unit="°C",
    )

    with pytest.raises(
        ValueError,
        match="^invalid_cloud_forecast_value$",
    ):
        compose_cloud_forecast_comparison(
            forecast_value,
            CloudCondition.CLEAR,
        )
