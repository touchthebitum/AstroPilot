from datetime import datetime, timedelta, timezone

import pytest

from decision.field_observation import (
    CaptureMethod,
    CloudCondition,
    FieldObservation,
    ObservationProvenance,
    ObservationQuality,
    ObservationSourceType,
    ObservedAcquisition,
    ObservedConditions,
    ObservedTechnical,
    SeeingCondition,
    SurfaceCondition,
    Transparency,
)
from decision.weather.cloud_forecast_evidence_comparison import (
    SelectedCloudForecastComparison,
)
from decision.weather.cloud_forecast_field_observation import (
    compare_cloud_forecast_to_field_observation,
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


OBSERVED_AT = datetime(2026, 9, 1, 21, 17, tzinfo=timezone.utc)
RETRIEVED_AT = OBSERVED_AT - timedelta(hours=2)
LOCATION = WeatherLocation(46.7508, 6.5495)


def observation(**overrides):
    cloud = overrides.pop("cloud_condition", CloudCondition.FEW)
    transparency = overrides.pop("transparency", None)
    seeing = overrides.pop("seeing", None)
    dew = overrides.pop("dew_detected", None)
    surface = (
        None if dew is None else SurfaceCondition.DEW_PRESENT
        if dew else SurfaceCondition.DRY
    )
    return FieldObservation(
        observation_id="observation-123",
        decision_id="decision-123",
        execution_id="execution-123",
        observed_at_utc=OBSERVED_AT,
        recorded_at_utc=OBSERVED_AT,
        supersedes_observation_id=None,
        conditions=ObservedConditions(
            cloud_state=cloud,
            transparency=transparency,
            seeing=seeing,
            surface_condition=surface,
        ),
        acquisition=ObservedAcquisition(),
        technical=ObservedTechnical(),
        provenance=ObservationProvenance(
            source_type=ObservationSourceType.USER,
            capture_method=CaptureMethod.MANUAL,
        ),
        quality=ObservationQuality(),
        **overrides,
    )


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


def compare(source, *points, maximum_minutes=30):
    return compare_cloud_forecast_to_field_observation(
        DecisionForecastEvidence(points),
        source,
        maximum_absolute_offset=timedelta(minutes=maximum_minutes),
    )


def test_observation_without_cloud_returns_none():
    source = observation(cloud_condition=None, dew_detected=False)

    assert compare(source, cloud_point(0, 85.0)) is None


def test_observation_timestamp_selects_forecast_and_condition_is_forwarded():
    farther = cloud_point(-20, 5.0)
    nearest = cloud_point(-4, 85.0)
    source = observation(cloud_condition=CloudCondition.PARTLY_CLOUDY)

    result = compare(source, farther, nearest)

    assert isinstance(result, SelectedCloudForecastComparison)
    assert result.forecast_point is nearest
    assert result.comparison.forecast_condition is CloudCondition.OVERCAST
    assert result.comparison.observed_condition is source.cloud_condition


def test_other_observation_dimensions_do_not_change_cloud_comparison():
    point = cloud_point(0, 5.0)
    source = observation(
        transparency=Transparency.POOR,
        seeing=SeeingCondition.EXCELLENT,
        dew_detected=True,
    )

    result = compare(source, point)

    assert result.forecast_point is point
    assert result.comparison.forecast_condition is CloudCondition.CLEAR
    assert result.comparison.observed_condition is source.cloud_condition


def test_present_cloud_without_admissible_forecast_returns_none():
    source = observation(cloud_condition=CloudCondition.OVERCAST)

    assert compare(source, cloud_point(31, 85.0)) is None


def test_ambiguous_forecasts_propagate_selection_error():
    with pytest.raises(
        ForecastTemporalSelectionError,
        match="^ambiguous_nearest_forecast$",
    ):
        compare(
            observation(),
            cloud_point(-5, 5.0),
            cloud_point(5, 85.0),
        )
