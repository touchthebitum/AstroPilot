"""Explain an absent evaluation without changing candidate eligibility."""
from datetime import timedelta, timezone
from math import isfinite

from astropilot.user_profile import resolve_minimum_altitude_deg
from decision.time_math import add_elapsed_time, timeline_value


def missing_target_refusal(*, sky, hours, target, catalog_key, profile, availability, lat, lon):
    minimum = resolve_minimum_altitude_deg(profile.get("preferences", {}))
    lower = availability.start if availability else None
    upper = availability.end if availability else None
    if availability and availability.start and availability.duration:
        upper = add_elapsed_time(lower, availability.duration)
    windows = sky.iter_windows(hours, profile.get("preferences", {}).get("window_size", 2))
    overlapping = [window for window in windows
                   if (lower is None or timeline_value(add_elapsed_time(window[-1]["time"], timedelta(hours=1))) > timeline_value(lower))
                   and (upper is None or timeline_value(window[0]["time"]) < timeline_value(upper))]
    samples = {hour["time"].astimezone(timezone.utc) for window in overlapping for hour in window}
    altitudes = [float(sky.target_altitude(target["ra"], target["dec"], time, lat, lon))
                 for time in sorted(samples, key=timeline_value)]
    below = bool(altitudes) and all(isfinite(a) and a < minimum for a in altitudes)
    return {
        "catalog_key": catalog_key,
        "code": "target_below_minimum_altitude" if below else "target_window_unavailable",
        "minimum_altitude_deg": minimum,
        "sample_count": len(altitudes),
        "window_start": lower.isoformat() if lower else None,
        "window_end": upper.isoformat() if upper else None,
    }
