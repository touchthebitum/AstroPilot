from datetime import datetime, timedelta

from decision.weather.cloud_forecast_value_extraction import (
    extract_cloud_forecast_value,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.forecast_temporal_candidates import (
    build_forecast_temporal_candidates,
)
from decision.weather.forecast_temporal_selection import (
    select_forecast_temporal_candidate,
)
from decision.weather.provider_reliability import WeatherForecastPoint


def select_cloud_forecast_point(
    evidence: DecisionForecastEvidence,
    observed_at_utc: datetime,
    *,
    maximum_absolute_offset: timedelta,
) -> WeatherForecastPoint | None:
    cloud_points = tuple(
        point
        for point in evidence.forecast_points
        if extract_cloud_forecast_value(point) is not None
    )
    candidates = build_forecast_temporal_candidates(
        cloud_points,
        observed_at_utc,
    )
    selected = select_forecast_temporal_candidate(
        candidates,
        maximum_absolute_offset=maximum_absolute_offset,
    )
    if selected is None:
        return None
    return selected.forecast_point
