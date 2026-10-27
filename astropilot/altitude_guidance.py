"""Read-only geometric aid, using production coordinates and astronomy only.

No weather fetch, decision, archive, mission or exposure credit is produced.
Intervals are conservative sampled bounds (one minute), not horizon predictions.
"""
from datetime import date, datetime, timedelta, timezone
from math import ceil, isfinite
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from astropilot.catalog import CATALOG
from astropilot.engines.sky_engine import SkyEngine
from astropilot.user_profile import resolve_minimum_altitude_deg
from decision.location.location_time import LocationTimeResolver
from decision.services.session_availability_windowing import MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW
from decision.services.tonight_application_service import resolve_tonight_inputs


class GuidanceError(ValueError):
    pass


class GuidancePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    time: AwareDatetime
    altitude_deg: float = Field(ge=-90, le=90, allow_inf_nan=False)


class GuidanceInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: AwareDatetime
    end: AwareDatetime
    duration_minutes: int = Field(gt=0)
    can_analyze: bool


class AltitudeGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["available", "no_altitude_window", "astronomical_night_unavailable"]
    project_id: str
    target_name: str
    site_name: str
    latitude: float
    longitude: float
    timezone: str
    night_date: date
    computed_at: AwareDatetime
    minimum_altitude_deg: float = Field(ge=0, le=90, allow_inf_nan=False)
    required_continuous_minutes: int
    sampling_minutes: Literal[1] = 1
    astronomical_only: Literal[True] = True
    night_start: AwareDatetime | None = None
    night_end: AwareDatetime | None = None
    points: tuple[GuidancePoint, ...] = ()
    intervals: tuple[GuidanceInterval, ...] = ()


def _ceil_minute(value):
    return datetime.fromtimestamp(ceil(value.timestamp() / 60) * 60, timezone.utc)


def _sampled_intervals(times, altitudes, minimum, now):
    """Use only consecutive samples >= threshold, never bridge a lower sample."""
    intervals = []
    start = None
    previous = None
    for time, altitude in zip(times, altitudes):
        if altitude >= minimum:
            if start is None:
                start = time
        elif start is not None:
            intervals.append((start, previous))
            start = None
        previous = time
    if start is not None:
        intervals.append((start, previous))
    required = int(MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW.total_seconds() // 60)
    result = []
    for lower, upper in intervals:
        lower = max(lower, _ceil_minute(now))
        minutes = int((upper - lower).total_seconds() // 60)
        if minutes > 0:
            result.append(GuidanceInterval(start=lower, end=upper,
                duration_minutes=minutes, can_analyze=minutes >= required))
    return tuple(result)


def altitude_guidance(*, profile, project_id, reference_time, night_date=None, sky=None):
    if not isinstance(profile, dict) or project_id not in profile.get("projects", {}):
        raise GuidanceError("guidance_project_unavailable")
    # Use exactly the production scoring catalogue, never guessed alias geometry.
    target = CATALOG.get(project_id)
    if not target or not all(isfinite(target.get(k, float("nan"))) for k in ("ra", "dec")):
        raise GuidanceError("guidance_coordinates_unavailable")
    inputs = resolve_tonight_inputs(profile)
    lat, lon = inputs.location["latitude"], inputs.location["longitude"]
    zone = LocationTimeResolver.resolve(lat, lon).zone
    if reference_time.utcoffset() is None:
        raise GuidanceError("guidance_time_unavailable")
    now = reference_time.astimezone(timezone.utc)
    today = now.astimezone(zone).date()
    sky = sky or SkyEngine()
    if night_date is None:
        night_date = today
        if now.astimezone(zone).hour < 12:
            try:
                _, dawn = sky.astronomical_night_window(today - timedelta(days=1), lat, lon, zone)
                if now < dawn.astimezone(timezone.utc):
                    night_date = today - timedelta(days=1)
            except ValueError:
                pass
    if not today - timedelta(days=1) <= night_date <= today + timedelta(days=14):
        raise GuidanceError("guidance_date_out_of_range")
    minimum = resolve_minimum_altitude_deg(profile.get("preferences", {}))
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not isfinite(minimum) or not 0 <= minimum <= 90:
        raise GuidanceError("guidance_threshold_unavailable")
    common = dict(project_id=project_id, target_name=target.get("name", project_id),
        site_name=inputs.location["name"], latitude=lat, longitude=lon, timezone=str(zone), night_date=night_date,
        computed_at=now, minimum_altitude_deg=minimum,
        required_continuous_minutes=int(MINIMUM_ACTIONABLE_PRODUCTIVE_WINDOW.total_seconds() // 60))
    try:
        dusk, dawn = sky.astronomical_night_window(night_date, lat, lon, zone)
    except ValueError:
        return AltitudeGuidance(status="astronomical_night_unavailable", **common)
    start = _ceil_minute(dusk)
    end = dawn.astimezone(timezone.utc).replace(second=0, microsecond=0)
    # Fail closed for unexpected or polar astronomy; keep the operation bounded.
    if not timedelta(0) < end - start <= timedelta(hours=24):
        return AltitudeGuidance(status="astronomical_night_unavailable", **common)
    times = [start + timedelta(minutes=i) for i in range(int((end-start).total_seconds()//60)+1)]
    values = [float(a) for a in sky.target_altitudes(target["ra"], target["dec"], times, lat, lon)]
    if len(values) != len(times) or any(not isfinite(a) or not -90 <= a <= 90 for a in values):
        raise GuidanceError("guidance_calculation_unavailable")
    intervals = _sampled_intervals(times, values, minimum, now)
    # Compact five-minute curve; threshold intervals retain one-minute precision.
    points = tuple(GuidancePoint(time=t, altitude_deg=round(a, 2))
                   for i, (t, a) in enumerate(zip(times, values)) if i % 5 == 0 or i == len(times)-1)
    return AltitudeGuidance(status="available" if intervals else "no_altitude_window",
        night_start=start, night_end=end, points=points, intervals=intervals, **common)
