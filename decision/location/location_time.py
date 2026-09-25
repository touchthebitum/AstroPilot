from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from timezonefinder import TimezoneFinder


class LocationTimeError(ValueError):
    code = "location_timezone_unresolved"


class LocalWallTimeError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_LOCAL_WALL_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"
)


def _parse_local_wall_time(value: str) -> datetime:
    if (
        not isinstance(value, str)
        or _LOCAL_WALL_TIME_PATTERN.fullmatch(value) is None
    ):
        raise LocalWallTimeError("session_availability_local_datetime_invalid")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise LocalWallTimeError(
            "session_availability_local_datetime_invalid"
        ) from exc


def _normalize_local_datetime(local_time: datetime, zone: ZoneInfo) -> datetime:
    if not isinstance(zone, ZoneInfo):
        raise LocalWallTimeError("session_availability_local_datetime_invalid")
    candidates = {}
    for fold in (0, 1):
        candidate = local_time.replace(tzinfo=zone, fold=fold)
        instant = candidate.astimezone(timezone.utc)
        round_trip = instant.astimezone(zone)
        if round_trip.replace(tzinfo=None) == local_time:
            candidates[instant] = candidate

    if not candidates:
        raise LocalWallTimeError(
            "session_availability_local_time_nonexistent"
        )
    if len(candidates) != 1:
        raise LocalWallTimeError(
            "session_availability_local_time_ambiguous"
        )
    return next(iter(candidates.values()))


def normalize_local_wall_time(value: str, zone: ZoneInfo) -> datetime:
    return _normalize_local_datetime(_parse_local_wall_time(value), zone)


def normalize_fixed_local_window(
    start_value: str,
    end_value: str,
    zone: ZoneInfo,
) -> tuple[datetime, datetime]:
    start_wall = _parse_local_wall_time(start_value)
    end_wall = _parse_local_wall_time(end_value)

    if end_wall.date() == start_wall.date():
        if end_wall.time() == start_wall.time():
            raise LocalWallTimeError(
                "session_availability_equal_times_ambiguous"
            )
        if end_wall.time() < start_wall.time():
            end_wall += timedelta(days=1)

    nominal_duration = end_wall - start_wall
    if nominal_duration <= timedelta(0):
        raise LocalWallTimeError(
            "session_availability_end_must_follow_start"
        )
    if nominal_duration > timedelta(hours=24):
        raise LocalWallTimeError(
            "session_availability_fixed_window_too_long"
        )

    start = _normalize_local_datetime(start_wall, zone)
    end = _normalize_local_datetime(end_wall, zone)
    if end.astimezone(timezone.utc) <= start.astimezone(timezone.utc):
        raise LocalWallTimeError(
            "session_availability_end_must_follow_start"
        )
    return start, end


@dataclass(frozen=True)
class LocationTime:
    latitude: float
    longitude: float
    timezone_name: str

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


class LocationTimeResolver:
    _finder = None

    @classmethod
    def _get_finder(cls):
        if cls._finder is None:
            cls._finder = TimezoneFinder(in_memory=True)
        return cls._finder

    @classmethod
    def resolve(cls, latitude: float, longitude: float) -> LocationTime:
        if (
            not isinstance(latitude, (int, float))
            or isinstance(latitude, bool)
            or not isfinite(float(latitude))
            or not -90 <= latitude <= 90
            or not isinstance(longitude, (int, float))
            or isinstance(longitude, bool)
            or not isfinite(float(longitude))
            or not -180 <= longitude <= 180
        ):
            raise LocationTimeError("invalid_coordinates")

        timezone_name = cls._get_finder().timezone_at(
            lat=float(latitude),
            lng=float(longitude),
        )
        if not timezone_name:
            raise LocationTimeError("timezone_not_found")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise LocationTimeError("timezone_not_supported") from exc

        return LocationTime(
            latitude=float(latitude),
            longitude=float(longitude),
            timezone_name=timezone_name,
        )
