from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from decision.weather.provider_reliability import WeatherForecastPoint


@dataclass(frozen=True)
class ForecastTemporalCandidate:
    forecast_point: WeatherForecastPoint
    temporal_offset: timedelta


def build_forecast_temporal_candidates(
    forecast_points: tuple[WeatherForecastPoint, ...],
    observed_at_utc: datetime,
) -> tuple[ForecastTemporalCandidate, ...]:
    if (
        not isinstance(observed_at_utc, datetime)
        or observed_at_utc.tzinfo is None
        or observed_at_utc.utcoffset() is None
    ):
        raise ValueError("invalid_observed_at_utc")
    observed_at = observed_at_utc.astimezone(timezone.utc)

    return tuple(
        ForecastTemporalCandidate(
            forecast_point=forecast_point,
            temporal_offset=forecast_point.forecast_for_utc - observed_at,
        )
        for forecast_point in forecast_points
    )
