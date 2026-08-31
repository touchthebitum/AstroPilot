from __future__ import annotations

from datetime import timedelta
from math import isfinite

from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import (
    WeatherForecastVerification,
    WeatherObservationPoint,
    compare_forecast_to_observation,
)


class FieldValidationTemporalPairingError(ValueError):
    pass


def _validate_tolerances(
    time_tolerance: timedelta,
    spatial_tolerance_km: float,
) -> None:
    if not isinstance(time_tolerance, timedelta) or time_tolerance < timedelta(0):
        raise ValueError("invalid_time_tolerance")
    if (
        isinstance(spatial_tolerance_km, bool)
        or not isinstance(spatial_tolerance_km, (int, float))
        or not isfinite(float(spatial_tolerance_km))
        or spatial_tolerance_km < 0
    ):
        raise ValueError("invalid_spatial_tolerance")


def compare_decision_forecast_evidence_to_observations(
    evidence: DecisionForecastEvidence,
    observations: tuple[WeatherObservationPoint, ...],
    *,
    time_tolerance: timedelta,
    spatial_tolerance_km: float,
) -> tuple[WeatherForecastVerification, ...]:
    _validate_tolerances(time_tolerance, spatial_tolerance_km)
    verifications = []

    for forecast in evidence.forecast_points:
        forecast_variables = {value.variable for value in forecast.values}
        candidates = tuple(
            observation
            for observation in observations
            if any(
                value.variable in forecast_variables for value in observation.values
            )
        )
        if not candidates:
            continue

        offsets = tuple(
            abs(observation.observed_at_utc - forecast.forecast_for_utc)
            for observation in candidates
        )
        nearest_offset = min(offsets)
        nearest = tuple(
            observation
            for observation, offset in zip(candidates, offsets)
            if offset == nearest_offset
        )
        if len(nearest) != 1:
            raise FieldValidationTemporalPairingError(
                "ambiguous_nearest_observation"
            )

        verifications.append(
            compare_forecast_to_observation(
                forecast,
                nearest[0],
                time_tolerance=time_tolerance,
                spatial_tolerance_km=spatial_tolerance_km,
            )
        )

    return tuple(verifications)
