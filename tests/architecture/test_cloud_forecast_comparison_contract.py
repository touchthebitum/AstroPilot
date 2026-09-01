from dataclasses import FrozenInstanceError, fields

import pytest

from decision.field_observation import CloudCondition
from decision.weather.cloud_forecast_comparison import (
    CloudForecastComparison,
    compare_cloud_conditions,
)


@pytest.mark.parametrize(
    ("forecast_condition", "observed_condition"),
    [
        (CloudCondition.CLEAR, CloudCondition.CLEAR),
        (CloudCondition.FEW, CloudCondition.MOSTLY_CLOUDY),
        (CloudCondition.OVERCAST, CloudCondition.CLEAR),
    ],
)
def test_compares_cloud_conditions_without_interpretation(
    forecast_condition,
    observed_condition,
):
    comparison = compare_cloud_conditions(
        forecast_condition,
        observed_condition,
    )

    assert isinstance(comparison, CloudForecastComparison)
    assert comparison.forecast_condition is forecast_condition
    assert comparison.observed_condition is observed_condition
    assert [field.name for field in fields(comparison)] == [
        "forecast_condition",
        "observed_condition",
    ]


def test_cloud_forecast_comparison_is_immutable():
    comparison = CloudForecastComparison(
        forecast_condition=CloudCondition.FEW,
        observed_condition=CloudCondition.OVERCAST,
    )

    with pytest.raises(FrozenInstanceError):
        comparison.forecast_condition = CloudCondition.CLEAR
