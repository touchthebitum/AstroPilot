from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from timezonefinder import TimezoneFinder


class LocationTimeError(ValueError):
    code = "location_timezone_unresolved"


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
