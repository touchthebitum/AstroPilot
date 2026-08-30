from __future__ import annotations

from datetime import timedelta

from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import (
    WeatherForecastVerification,
    WeatherObservationPoint,
    compare_forecast_to_observation,
)


def compare_decision_forecast_evidence(
    evidence: DecisionForecastEvidence,
    observation: WeatherObservationPoint,
    *,
    time_tolerance: timedelta,
    spatial_tolerance_km: float,
) -> tuple[WeatherForecastVerification, ...]:
    observed_variables = {value.variable for value in observation.values}
    candidates = (
        forecast
        for forecast in evidence.forecast_points
        if any(value.variable in observed_variables for value in forecast.values)
    )
    return tuple(
        compare_forecast_to_observation(
            forecast,
            observation,
            time_tolerance=time_tolerance,
            spatial_tolerance_km=spatial_tolerance_km,
        )
        for forecast in candidates
    )
