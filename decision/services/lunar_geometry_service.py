from __future__ import annotations

from datetime import datetime
from math import atan2, cos, isfinite, sin

import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
from astropy.time import Time
from astropy.utils import iers

from decision.models.context.site_context import SiteContext
from decision.models.imaging_field_geometry import (
    ImagingFieldGeometryDefinition,
)
from decision.models.lunar_geometry import LunarGeometry


class LunarGeometryService:
    """Calculate canonical lunar geometry using Astropy ephemerides."""

    @classmethod
    def calculate(
        cls,
        *,
        reference_time: datetime,
        site: SiteContext,
        field_geometry: ImagingFieldGeometryDefinition,
    ) -> LunarGeometry:
        cls._validate_reference_time(reference_time)
        latitude, longitude, elevation = cls._validate_site(site)
        if not isinstance(
            field_geometry,
            ImagingFieldGeometryDefinition,
        ):
            raise TypeError(
                "field_geometry must be an "
                "ImagingFieldGeometryDefinition"
            )

        location = EarthLocation.from_geodetic(
            lon=longitude * u.deg,
            lat=latitude * u.deg,
            height=elevation * u.m,
        )
        observation_time = Time(reference_time)
        apparent_frame = AltAz(
            obstime=observation_time,
            location=location,
            pressure=0 * u.hPa,
        )

        # Astropy's bundled IERS data is sufficient for this deterministic,
        # offline calculation. Keep the network policy local to this call.
        with iers.conf.set_temp("auto_download", False):
            moon = get_body(
                "moon",
                observation_time,
                location=location,
            )
            sun = get_body(
                "sun",
                observation_time,
                location=location,
            )
            moon_apparent = moon.transform_to(apparent_frame)
            field_apparent = SkyCoord(
                ra=field_geometry.reference_ra_deg * u.deg,
                dec=field_geometry.reference_dec_deg * u.deg,
                frame="icrs",
            ).transform_to(apparent_frame)

        illumination = cls._moon_illumination(sun=sun, moon=moon)
        return LunarGeometry(
            moon_illumination=illumination,
            moon_altitude_deg=float(moon_apparent.alt.to_value(u.deg)),
            moon_separation_deg=float(
                moon_apparent.separation(field_apparent).to_value(u.deg)
            ),
        )

    @staticmethod
    def _moon_illumination(*, sun: SkyCoord, moon: SkyCoord) -> float:
        """Return the illuminated fraction from the Sun-Moon phase angle."""
        elongation = sun.separation(moon).to_value(u.rad)
        sun_distance_km = sun.distance.to_value(u.km)
        moon_distance_km = moon.distance.to_value(u.km)
        phase_angle = atan2(
            sun_distance_km * sin(elongation),
            moon_distance_km - sun_distance_km * cos(elongation),
        )
        return float((1.0 + cos(phase_angle)) / 2.0)

    @staticmethod
    def _validate_reference_time(reference_time: datetime) -> None:
        if not isinstance(reference_time, datetime):
            raise TypeError("reference_time must be a datetime")
        if (
            reference_time.tzinfo is None
            or reference_time.utcoffset() is None
        ):
            raise ValueError("reference_time must be timezone-aware")

    @classmethod
    def _validate_site(
        cls,
        site: SiteContext,
    ) -> tuple[float, float, float]:
        if not isinstance(site, SiteContext):
            raise TypeError("site must be a SiteContext")

        latitude = cls._validate_site_value(
            site.latitude,
            "latitude",
            minimum=-90.0,
            maximum=90.0,
        )
        longitude = cls._validate_site_value(
            site.longitude,
            "longitude",
            minimum=-180.0,
            maximum=180.0,
        )
        elevation = cls._validate_site_value(site.elevation, "elevation")
        return latitude, longitude, elevation

    @staticmethod
    def _validate_site_value(
        value: float,
        name: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
        ):
            raise ValueError(f"{name} must be a finite number")
        numeric_value = float(value)
        if minimum is not None and numeric_value < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
        if maximum is not None and numeric_value > maximum:
            raise ValueError(f"{name} must be at most {maximum}")
        return numeric_value
