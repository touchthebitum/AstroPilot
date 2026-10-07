"""Validate explicit productivity inputs without inventing meteorological evidence."""
from math import ceil, isfinite


RANGES = {
    "cloud_cover": (0, 100),
    "humidity": (0, 100),
    "wind": (0, None),
    "seeing": (0, None),
    "moon_penalty": (0, 1),
}
SERIES = {
    "cloud_cover": "hourly_clouds",
    "humidity": "hourly_humidity",
    "wind": "hourly_wind",
    "seeing": "hourly_seeing",
    "moon_penalty": "hourly_moon_penalty",
}


def valid_number(value, minimum=0, maximum=None, *, positive=False):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and (value > minimum if positive else value >= minimum)
        and (maximum is None or value <= maximum)
    )


def evidence_issues(context):
    """Scalar inputs are explicit evidence; a supplied series must cover the horizon."""
    issues = []
    hours = context.astronomical_hours
    if not valid_number(hours, positive=True):
        issues.append("astronomical_hours_missing_or_invalid")
    required = ceil(hours) if not issues else 0
    for metric, (minimum, maximum) in RANGES.items():
        scalar = getattr(context, metric, None)
        if not valid_number(scalar, minimum, maximum, positive=metric == "seeing"):
            issues.append(f"{metric}_missing_or_invalid")
        name = SERIES[metric]
        weather = getattr(context, "weather", None)
        values = getattr(weather, name, None) if weather is not None else None
        if weather is not None and values is None:
            issues.append(f"{name}_missing")
        if values is None and weather is None:
            values = getattr(context, name, None)
        if values is not None and (
            not isinstance(values, (list, tuple))
            or len(values) < required
            or not all(valid_number(v, minimum, maximum, positive=metric == "seeing") for v in values)
        ):
            issues.append(f"{name}_incomplete_or_invalid")
    return tuple(issues)
