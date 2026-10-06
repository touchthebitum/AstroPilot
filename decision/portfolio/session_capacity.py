"""Explicit session/scenario duration for gain contributions, not observed evidence."""
import math


def explicit_session_hours(value: float | None) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        return 0.0
    return float(value)
