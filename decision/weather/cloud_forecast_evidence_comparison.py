from dataclasses import dataclass
from datetime import datetime, timedelta

from decision.field_observation import CloudCondition
from decision.weather.cloud_forecast_comparison import CloudForecastComparison
from decision.weather.cloud_forecast_composition import (
    compose_cloud_forecast_comparison,
)
from decision.weather.cloud_forecast_temporal_selection import (
    select_cloud_forecast_point,
)
from decision.weather.cloud_forecast_value_extraction import (
    extract_cloud_forecast_value,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import WeatherForecastPoint


@dataclass(frozen=True)
class SelectedCloudForecastComparison:
    forecast_point: WeatherForecastPoint
    comparison: CloudForecastComparison


def compare_cloud_forecast_evidence(
    evidence: DecisionForecastEvidence,
    observed_at_utc: datetime,
    observed_condition: CloudCondition,
    *,
    maximum_absolute_offset: timedelta,
) -> SelectedCloudForecastComparison | None:
    selected_point = select_cloud_forecast_point(
        evidence,
        observed_at_utc,
        maximum_absolute_offset=maximum_absolute_offset,
    )
    if selected_point is None:
        return None

    forecast_value = extract_cloud_forecast_value(selected_point)
    assert forecast_value is not None

    comparison = compose_cloud_forecast_comparison(
        forecast_value,
        observed_condition,
    )
    return SelectedCloudForecastComparison(
        forecast_point=selected_point,
        comparison=comparison,
    )
