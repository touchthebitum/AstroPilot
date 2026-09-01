from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone

import pytest

from decision.field_observation import CloudCondition
from decision.weather.cloud_forecast_comparison import CloudForecastComparison
from decision.weather.cloud_forecast_evidence_comparison import (
    SelectedCloudForecastComparison,
    compare_cloud_forecast_evidence,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.forecast_temporal_selection import (
    ForecastTemporalSelectionError,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)
RETRIEVED_AT = OBSERVED_AT - timedelta(hours=2)
LOCATION = WeatherLocation(46.7508, 6.5495)


def cloud_point(offset_minutes, cloud_cover_percent):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=RETRIEVED_AT,
        forecast_for_utc=OBSERVED_AT + timedelta(minutes=offset_minutes),
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=(
            WeatherValue(
                variable=WeatherVariable.CLOUD_COVER_PERCENT,
                value=cloud_cover_percent,
                unit="%",
            ),
        ),
    )


def compare(*points, maximum_minutes=30, observed=CloudCondition.FEW):
    return compare_cloud_forecast_evidence(
        DecisionForecastEvidence(points),
        OBSERVED_AT,
        observed,
        maximum_absolute_offset=timedelta(minutes=maximum_minutes),
    )


def test_result_is_frozen_and_has_exactly_two_fields():
    point = cloud_point(0, 5.0)
    comparison = CloudForecastComparison(
        forecast_condition=CloudCondition.CLEAR,
        observed_condition=CloudCondition.FEW,
    )
    result = SelectedCloudForecastComparison(point, comparison)

    assert [field.name for field in fields(result)] == [
        "forecast_point",
        "comparison",
    ]
    with pytest.raises(FrozenInstanceError):
        result.forecast_point = cloud_point(1, 85.0)


def test_empty_evidence_returns_none():
    assert compare() is None


def test_single_cloud_point_preserves_provenance_and_composes_conditions():
    point = cloud_point(10, 42.0)

    result = compare(point, observed=CloudCondition.OVERCAST)

    assert isinstance(result, SelectedCloudForecastComparison)
    assert result.forecast_point is point
    assert isinstance(result.comparison, CloudForecastComparison)
    assert result.comparison.forecast_condition is CloudCondition.PARTLY_CLOUDY
    assert result.comparison.observed_condition is CloudCondition.OVERCAST


def test_comparison_comes_from_the_temporally_selected_cloud_point():
    earlier = cloud_point(-20, 5.0)
    nearest = cloud_point(-5, 85.0)

    result = compare(earlier, nearest, observed=CloudCondition.FEW)

    assert result.forecast_point is nearest
    assert result.comparison.forecast_condition is CloudCondition.OVERCAST
    assert result.comparison.observed_condition is CloudCondition.FEW


def test_maximum_absolute_offset_is_forwarded_to_selection():
    outside = cloud_point(10, 85.0)

    assert compare(outside, maximum_minutes=5) is None


def test_ambiguous_selection_error_propagates_unchanged():
    with pytest.raises(
        ForecastTemporalSelectionError,
        match="^ambiguous_nearest_forecast$",
    ):
        compare(cloud_point(-5, 5.0), cloud_point(5, 85.0))
