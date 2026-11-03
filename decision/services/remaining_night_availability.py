"""Bind an undated all-night commitment to the remaining astronomical night.

Use the request's explicit clock, never the machine clock. The returned bounds
are shared by ranking, eligibility and mission construction; saved requests and
historical results are not rewritten.
"""
from datetime import timedelta, timezone

from astropilot.engines.sky_engine import SkyEngine
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode


def remaining_night_availability(availability, *, reference_time_utc, latitude,
                                 longitude, zone):
    if availability is None or availability.mode is not SessionAvailabilityMode.ALL_NIGHT:
        return availability
    if reference_time_utc.utcoffset() is None:
        raise ValueError("reference_time_without_timezone")
    now = reference_time_utc.astimezone(timezone.utc)
    local_now = now.astimezone(zone)
    evening = local_now.date()
    if local_now.hour < 12:
        previous = evening - timedelta(days=1)
        _, dawn = SkyEngine.astronomical_night_window(previous, latitude, longitude, zone)
        if now < dawn.astimezone(timezone.utc):
            evening = previous
    dusk, dawn = SkyEngine.astronomical_night_window(evening, latitude, longitude, zone)
    return SessionAvailability(
        SessionAvailabilityMode.FIXED_WINDOW,
        start=max(dusk.astimezone(timezone.utc), now).astimezone(zone),
        end=dawn,
    )
