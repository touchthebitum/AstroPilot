from __future__ import annotations

from datetime import datetime, timezone

from decision.weather.weather_ingress import WeatherSnapshot


class WeatherWindowCoverageError(ValueError):
    code = "weather_window_uncovered"

    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = tuple(issues)


def validate_selected_window_weather_coverage(
    mission,
    snapshot: WeatherSnapshot,
) -> None:
    start = getattr(mission, "window_start", None)
    end = getattr(mission, "window_end", None)
    if (
        not isinstance(start, datetime)
        or start.tzinfo is None
        or not isinstance(end, datetime)
        or end.tzinfo is None
    ):
        raise WeatherWindowCoverageError(["invalid_mission_window"])
    if snapshot.valid_from.tzinfo is None or snapshot.valid_until.tzinfo is None:
        raise WeatherWindowCoverageError(["invalid_weather_coverage"])

    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    valid_from_utc = snapshot.valid_from.astimezone(timezone.utc)
    valid_until_utc = snapshot.valid_until.astimezone(timezone.utc)

    issues = []
    if start_utc < valid_from_utc:
        issues.append("window_starts_before_weather")
    if end_utc > valid_until_utc:
        issues.append("window_ends_after_weather")
    if issues:
        raise WeatherWindowCoverageError(issues)
