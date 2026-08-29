from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Literal


class WeatherVariable(str, Enum):
    CLOUD_COVER_PERCENT = "cloud_cover_percent"
    PRECIPITATION_MM = "precipitation_mm"
    RELATIVE_HUMIDITY_PERCENT = "relative_humidity_percent"
    VISIBILITY_M = "visibility_m"
    WIND_SPEED_KMH = "wind_speed_kmh"
    TEMPERATURE_C = "temperature_c"


CANONICAL_UNITS = {
    WeatherVariable.CLOUD_COVER_PERCENT: "%",
    WeatherVariable.PRECIPITATION_MM: "mm",
    WeatherVariable.RELATIVE_HUMIDITY_PERCENT: "%",
    WeatherVariable.VISIBILITY_M: "m",
    WeatherVariable.WIND_SPEED_KMH: "km/h",
    WeatherVariable.TEMPERATURE_C: "°C",
}

VALUE_RANGES = {
    WeatherVariable.CLOUD_COVER_PERCENT: (0.0, 100.0),
    WeatherVariable.PRECIPITATION_MM: (0.0, None),
    WeatherVariable.RELATIVE_HUMIDITY_PERCENT: (0.0, 100.0),
    WeatherVariable.VISIBILITY_M: (0.0, None),
    WeatherVariable.WIND_SPEED_KMH: (0.0, None),
    WeatherVariable.TEMPERATURE_C: (-100.0, 60.0),
}


def _finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid_{name}")
    return value.strip()


@dataclass(frozen=True)
class WeatherLocation:
    latitude: float
    longitude: float

    def __post_init__(self):
        if not _finite_number(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("invalid_latitude")
        if not _finite_number(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("invalid_longitude")
        object.__setattr__(self, "latitude", float(self.latitude))
        object.__setattr__(self, "longitude", float(self.longitude))


@dataclass(frozen=True)
class WeatherValue:
    variable: WeatherVariable
    value: float
    unit: str
    aggregation_period: timedelta | None = None

    def __post_init__(self):
        if not isinstance(self.variable, WeatherVariable):
            raise ValueError("unknown_weather_variable")
        if self.unit != CANONICAL_UNITS[self.variable]:
            raise ValueError("non_canonical_unit")
        if not _finite_number(self.value):
            raise ValueError("non_finite_weather_value")
        lower, upper = VALUE_RANGES[self.variable]
        numeric = float(self.value)
        if numeric < lower or (upper is not None and numeric > upper):
            raise ValueError("weather_value_out_of_range")
        if self.variable is WeatherVariable.PRECIPITATION_MM:
            if (
                not isinstance(self.aggregation_period, timedelta)
                or self.aggregation_period <= timedelta(0)
            ):
                raise ValueError("precipitation_aggregation_period_required")
        elif self.aggregation_period is not None:
            raise ValueError("aggregation_period_not_supported")
        object.__setattr__(self, "value", numeric)


def _values_by_variable(values: tuple[WeatherValue, ...], name: str):
    normalized = tuple(values)
    if not normalized:
        raise ValueError(f"{name}_values_required")
    if any(not isinstance(value, WeatherValue) for value in normalized):
        raise ValueError(f"invalid_{name}_value")
    variables = [value.variable for value in normalized]
    if len(set(variables)) != len(variables):
        raise ValueError(f"duplicate_{name}_variable")
    return normalized


@dataclass(frozen=True)
class WeatherForecastPoint:
    provider_id: str
    retrieved_at_utc: datetime
    forecast_for_utc: datetime
    requested_location: WeatherLocation
    grid_location: WeatherLocation
    values: tuple[WeatherValue, ...]
    model_id: str | None = None

    def __post_init__(self):
        retrieved = _utc(self.retrieved_at_utc, "retrieved_at")
        forecast_for = _utc(self.forecast_for_utc, "forecast_for")
        if forecast_for < retrieved:
            raise ValueError("forecast_captured_after_valid_time")
        if not isinstance(self.requested_location, WeatherLocation):
            raise ValueError("invalid_requested_location")
        if not isinstance(self.grid_location, WeatherLocation):
            raise ValueError("invalid_grid_location")
        object.__setattr__(self, "provider_id", _identity(self.provider_id, "provider_id"))
        object.__setattr__(self, "retrieved_at_utc", retrieved)
        object.__setattr__(self, "forecast_for_utc", forecast_for)
        object.__setattr__(
            self,
            "values",
            _values_by_variable(self.values, "forecast"),
        )
        if self.model_id is not None:
            object.__setattr__(self, "model_id", _identity(self.model_id, "model_id"))

    @property
    def horizon(self) -> timedelta:
        return self.forecast_for_utc - self.retrieved_at_utc


@dataclass(frozen=True)
class WeatherObservationPoint:
    source_id: str
    observed_at_utc: datetime
    location: WeatherLocation
    values: tuple[WeatherValue, ...]
    quality_status: Literal["validated", "rejected"] = "validated"

    def __post_init__(self):
        if not isinstance(self.location, WeatherLocation):
            raise ValueError("invalid_observation_location")
        if self.quality_status not in ("validated", "rejected"):
            raise ValueError("invalid_observation_quality_status")
        object.__setattr__(self, "source_id", _identity(self.source_id, "source_id"))
        object.__setattr__(
            self,
            "observed_at_utc",
            _utc(self.observed_at_utc, "observed_at"),
        )
        object.__setattr__(
            self,
            "values",
            _values_by_variable(self.values, "observation"),
        )


class ComparisonStatus(str, Enum):
    COMPARABLE = "comparable"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True)
class WeatherVariableError:
    variable: WeatherVariable
    forecast_value: float
    observed_value: float
    unit: str
    signed_error: float
    absolute_error: float


@dataclass(frozen=True)
class WeatherForecastVerification:
    provider_id: str
    status: ComparisonStatus
    horizon: timedelta
    time_difference: timedelta
    distance_km: float
    model_id: str | None = None
    errors: tuple[WeatherVariableError, ...] = ()
    reasons: tuple[str, ...] = ()
    unmatched_variables: tuple[WeatherVariable, ...] = ()


def _distance_km(first: WeatherLocation, second: WeatherLocation) -> float:
    earth_radius_km = 6371.0
    delta_lat = radians(second.latitude - first.latitude)
    delta_lon = radians(second.longitude - first.longitude)
    first_latitude = radians(first.latitude)
    second_latitude = radians(second.latitude)
    value = (
        sin(delta_lat / 2) ** 2
        + cos(first_latitude)
        * cos(second_latitude)
        * sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * asin(sqrt(value))


def compare_forecast_to_observation(
    forecast: WeatherForecastPoint,
    observation: WeatherObservationPoint,
    *,
    time_tolerance: timedelta,
    spatial_tolerance_km: float,
) -> WeatherForecastVerification:
    if not isinstance(time_tolerance, timedelta) or time_tolerance < timedelta(0):
        raise ValueError("invalid_time_tolerance")
    if not _finite_number(spatial_tolerance_km) or spatial_tolerance_km < 0:
        raise ValueError("invalid_spatial_tolerance")

    time_difference = abs(observation.observed_at_utc - forecast.forecast_for_utc)
    distance = _distance_km(forecast.grid_location, observation.location)
    reasons = []
    if observation.quality_status != "validated":
        reasons.append("observation_rejected")
    if time_difference > time_tolerance:
        reasons.append("observation_time_outside_tolerance")
    if distance > spatial_tolerance_km:
        reasons.append("observation_location_outside_tolerance")

    forecast_values = {value.variable: value for value in forecast.values}
    observation_values = {value.variable: value for value in observation.values}
    common = sorted(
        forecast_values.keys() & observation_values.keys(),
        key=lambda variable: variable.value,
    )
    unmatched = tuple(
        sorted(
            forecast_values.keys() ^ observation_values.keys(),
            key=lambda variable: variable.value,
        )
    )
    if not common:
        reasons.append("no_comparable_variables")

    for variable in common:
        predicted = forecast_values[variable]
        observed = observation_values[variable]
        if predicted.aggregation_period != observed.aggregation_period:
            reasons.append(f"aggregation_period_mismatch:{variable.value}")

    if reasons:
        return WeatherForecastVerification(
            provider_id=forecast.provider_id,
            model_id=forecast.model_id,
            status=ComparisonStatus.NOT_COMPARABLE,
            horizon=forecast.horizon,
            time_difference=time_difference,
            distance_km=distance,
            reasons=tuple(reasons),
            unmatched_variables=unmatched,
        )

    errors = []
    for variable in common:
        predicted = forecast_values[variable]
        observed = observation_values[variable]
        signed_error = predicted.value - observed.value
        errors.append(
            WeatherVariableError(
                variable=variable,
                forecast_value=predicted.value,
                observed_value=observed.value,
                unit=predicted.unit,
                signed_error=signed_error,
                absolute_error=abs(signed_error),
            )
        )
    return WeatherForecastVerification(
        provider_id=forecast.provider_id,
        model_id=forecast.model_id,
        status=ComparisonStatus.COMPARABLE,
        horizon=forecast.horizon,
        time_difference=time_difference,
        distance_km=distance,
        errors=tuple(errors),
        unmatched_variables=unmatched,
    )
