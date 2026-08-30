from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from decision.weather.provider_reliability import (
    CANONICAL_UNITS,
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)
from decision.weather.weather_ingress import WeatherSnapshot


_ROW_VARIABLES = (
    ("temperature_2m", WeatherVariable.TEMPERATURE_C),
    ("relative_humidity_2m", WeatherVariable.RELATIVE_HUMIDITY_PERCENT),
    ("wind_speed_10m", WeatherVariable.WIND_SPEED_KMH),
)


@dataclass(frozen=True)
class DecisionForecastEvidence:
    forecast_points: tuple[WeatherForecastPoint, ...]

    def __post_init__(self):
        points = tuple(self.forecast_points)
        if any(not isinstance(point, WeatherForecastPoint) for point in points):
            raise ValueError("invalid_decision_forecast_point")
        object.__setattr__(self, "forecast_points", points)


def _row_valid_at(row: dict) -> datetime:
    valid_at = row.get("time") if isinstance(row, dict) else None
    if not isinstance(valid_at, datetime) or valid_at.tzinfo is None:
        raise ValueError("invalid_hourly_row_time")
    return valid_at.astimezone(timezone.utc)


def build_decision_forecast_evidence(
    snapshot: WeatherSnapshot,
    hourly_rows: list[dict] | tuple[dict, ...],
) -> DecisionForecastEvidence:
    if not isinstance(snapshot, WeatherSnapshot):
        raise ValueError("weather_snapshot_required")

    retrieved_at = snapshot.retrieved_at_utc.astimezone(timezone.utc)
    requested_location = WeatherLocation(
        snapshot.requested_latitude,
        snapshot.requested_longitude,
    )
    grid_location = WeatherLocation(
        snapshot.grid_latitude,
        snapshot.grid_longitude,
        altitude_m=snapshot.elevation_m,
    )
    admissible_rows = []
    for row in tuple(hourly_rows):
        valid_at = _row_valid_at(row)
        if valid_at >= retrieved_at:
            admissible_rows.append((valid_at, row))
    admissible_rows.sort(key=lambda item: item[0])

    points = []
    for valid_at, row in admissible_rows:
        for row_key, variable in _ROW_VARIABLES:
            points.append(
                WeatherForecastPoint(
                    provider_id=snapshot.provider,
                    model_id=None,
                    retrieved_at_utc=snapshot.retrieved_at_utc,
                    forecast_for_utc=valid_at,
                    requested_location=requested_location,
                    grid_location=grid_location,
                    values=(
                        WeatherValue(
                            variable=variable,
                            value=row[row_key],
                            unit=CANONICAL_UNITS[variable],
                        ),
                    ),
                )
            )

    return DecisionForecastEvidence(forecast_points=tuple(points))
