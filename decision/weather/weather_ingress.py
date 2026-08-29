from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROVIDER = "Open-Meteo"
REQUIRED_HOURLY_UNITS = {
    "cloud_cover": "%",
    "cloud_cover_low": "%",
    "cloud_cover_mid": "%",
    "cloud_cover_high": "%",
    "precipitation": "mm",
    "relative_humidity_2m": "%",
    "visibility": "m",
    "wind_speed_10m": "km/h",
    "temperature_2m": "°C",
}
VALUE_RANGES = {
    "cloud_cover": (0.0, 100.0),
    "cloud_cover_low": (0.0, 100.0),
    "cloud_cover_mid": (0.0, 100.0),
    "cloud_cover_high": (0.0, 100.0),
    "precipitation": (0.0, None),
    "relative_humidity_2m": (0.0, 100.0),
    "visibility": (0.0, None),
    "wind_speed_10m": (0.0, None),
    "temperature_2m": (-100.0, 60.0),
}
MINIMUM_HOURLY_COVERAGE = 24
MAXIMUM_GRID_DISTANCE_KM = 50.0
MAXIMUM_SNAPSHOT_AGE = timedelta(minutes=90)
FUTURE_RETRIEVAL_TOLERANCE = timedelta(minutes=5)


class WeatherIngressError(ValueError):
    code = "weather_invalid"

    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = tuple(issues)


class WeatherInsufficientError(WeatherIngressError):
    code = "weather_insufficient"


class WeatherStaleError(WeatherIngressError):
    code = "weather_stale"


@dataclass(frozen=True)
class WeatherFreshness:
    snapshot_age_minutes: float
    freshness_status: Literal["fresh"]
    maximum_age_minutes: int


@dataclass(frozen=True)
class WeatherSnapshot:
    payload: dict[str, Any]
    provider: str
    retrieved_at_utc: datetime
    requested_latitude: float
    requested_longitude: float
    grid_latitude: float
    grid_longitude: float
    grid_distance_km: float
    elevation_m: float | None
    timezone: str
    timezone_source: str
    utc_offset_seconds: int
    valid_from: datetime
    valid_until: datetime
    hour_count: int
    completeness: float

    def trust_transport(
        self,
        freshness: WeatherFreshness | None = None,
    ) -> dict[str, Any]:
        transport = {
            "provider": self.provider,
            "retrieved_at_utc": self.retrieved_at_utc.isoformat(),
            "requested_latitude": self.requested_latitude,
            "requested_longitude": self.requested_longitude,
            "grid_latitude": self.grid_latitude,
            "grid_longitude": self.grid_longitude,
            "grid_distance_km": self.grid_distance_km,
            "elevation_m": self.elevation_m,
            "timezone": self.timezone,
            "timezone_source": self.timezone_source,
            "utc_offset_seconds": self.utc_offset_seconds,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "hour_count": self.hour_count,
            "completeness": self.completeness,
            "validation_status": "validated",
        }
        if freshness is not None:
            transport.update(
                snapshot_age_minutes=freshness.snapshot_age_minutes,
                freshness_status=freshness.freshness_status,
                maximum_age_minutes=freshness.maximum_age_minutes,
            )
        return transport


def validate_weather_freshness(
    snapshot: WeatherSnapshot,
    *,
    reference_time_utc: datetime,
    maximum_age: timedelta = MAXIMUM_SNAPSHOT_AGE,
    future_tolerance: timedelta = FUTURE_RETRIEVAL_TOLERANCE,
) -> WeatherFreshness:
    if reference_time_utc.tzinfo is None:
        raise WeatherIngressError(["reference_time_without_timezone"])
    if snapshot.retrieved_at_utc.tzinfo is None:
        raise WeatherIngressError(["retrieval_time_without_timezone"])
    if maximum_age < timedelta(0):
        raise ValueError("maximum_age must not be negative")
    if future_tolerance < timedelta(0):
        raise ValueError("future_tolerance must not be negative")

    age = (
        reference_time_utc.astimezone(timezone.utc)
        - snapshot.retrieved_at_utc.astimezone(timezone.utc)
    )
    if age < -future_tolerance:
        raise WeatherIngressError(["retrieval_time_in_future"])
    if age > maximum_age:
        raise WeatherStaleError(["retrieval_time_too_old"])

    return WeatherFreshness(
        snapshot_age_minutes=round(max(0.0, age.total_seconds() / 60.0), 2),
        freshness_status="fresh",
        maximum_age_minutes=int(maximum_age.total_seconds() / 60),
    )


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _grid_distance_km(lat1: float, lon1: float, lat2: float, lon2: float):
    earth_radius_km = 6371.0
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    start_lat = radians(lat1)
    end_lat = radians(lat2)
    value = (
        sin(delta_lat / 2) ** 2
        + cos(start_lat) * cos(end_lat) * sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * asin(sqrt(value))


def validate_weather_payload(
    payload: dict[str, Any],
    *,
    requested_latitude: float,
    requested_longitude: float,
    requested_timezone: str,
    retrieved_at_utc: datetime | None = None,
) -> WeatherSnapshot:
    if not isinstance(payload, dict):
        raise WeatherIngressError(["response_not_object"])
    if payload.get("error") is True:
        raise WeatherIngressError(["provider_error_response"])

    issues = []
    for name in ("latitude", "longitude", "utc_offset_seconds"):
        if not _number(payload.get(name)):
            issues.append(f"invalid_{name}")

    response_timezone = payload.get("timezone")
    if response_timezone != requested_timezone:
        issues.append("unexpected_timezone")
    try:
        zone = ZoneInfo(response_timezone) if isinstance(response_timezone, str) else None
    except ZoneInfoNotFoundError:
        zone = None
        issues.append("unknown_timezone")

    units = payload.get("hourly_units")
    if not isinstance(units, dict):
        issues.append("missing_hourly_units")
        units = {}
    if units.get("time") != "unixtime":
        issues.append("invalid_unit_time")
    for name, expected in REQUIRED_HOURLY_UNITS.items():
        if units.get(name) != expected:
            issues.append(f"invalid_unit_{name}")

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise WeatherIngressError([*issues, "missing_hourly"])
    times = hourly.get("time")
    if not isinstance(times, list):
        raise WeatherIngressError([*issues, "missing_hourly_time"])
    hour_count = len(times)

    for name in REQUIRED_HOURLY_UNITS:
        values = hourly.get(name)
        if not isinstance(values, list):
            issues.append(f"missing_series_{name}")
            continue
        if len(values) != hour_count:
            issues.append(f"misaligned_series_{name}")
            continue
        lower, upper = VALUE_RANGES[name]
        for value in values:
            if not _number(value):
                issues.append(f"invalid_value_{name}")
                break
            numeric = float(value)
            if numeric < lower or (upper is not None and numeric > upper):
                issues.append(f"out_of_range_{name}")
                break

    parsed_times = []
    for value in times:
        if not _number(value):
            issues.append("invalid_hourly_time")
            break
        if zone is None:
            break
        try:
            parsed_times.append(
                datetime.fromtimestamp(float(value), timezone.utc).astimezone(zone)
            )
        except (OverflowError, OSError, ValueError):
            issues.append("invalid_hourly_time")
            break

    if len(parsed_times) == hour_count:
        utc_times = [value.astimezone(timezone.utc) for value in parsed_times]
        if any(
            current <= previous
            for previous, current in zip(utc_times, utc_times[1:])
        ):
            issues.append("non_monotonic_hourly_time")
        elif any(
            current - previous != timedelta(hours=1)
            for previous, current in zip(utc_times, utc_times[1:])
        ):
            issues.append("non_hourly_time_cadence")

    if issues:
        raise WeatherIngressError(issues)
    if hour_count < MINIMUM_HOURLY_COVERAGE:
        raise WeatherInsufficientError(["hourly_coverage_below_24"])

    grid_latitude = float(payload["latitude"])
    grid_longitude = float(payload["longitude"])
    distance = _grid_distance_km(
        requested_latitude,
        requested_longitude,
        grid_latitude,
        grid_longitude,
    )
    if distance > MAXIMUM_GRID_DISTANCE_KM:
        raise WeatherIngressError(["weather_grid_too_far"])

    retrieved = retrieved_at_utc or datetime.now(timezone.utc)
    if retrieved.tzinfo is None:
        raise WeatherIngressError(["retrieval_time_without_timezone"])

    elevation = payload.get("elevation")
    if elevation is not None and not _number(elevation):
        raise WeatherIngressError(["invalid_elevation"])

    return WeatherSnapshot(
        payload=payload,
        provider=PROVIDER,
        retrieved_at_utc=retrieved.astimezone(timezone.utc),
        requested_latitude=float(requested_latitude),
        requested_longitude=float(requested_longitude),
        grid_latitude=grid_latitude,
        grid_longitude=grid_longitude,
        grid_distance_km=round(distance, 2),
        elevation_m=float(elevation) if elevation is not None else None,
        timezone=response_timezone,
        timezone_source="coordinates_local",
        utc_offset_seconds=int(payload["utc_offset_seconds"]),
        valid_from=parsed_times[0],
        valid_until=parsed_times[-1],
        hour_count=hour_count,
        completeness=1.0,
    )
