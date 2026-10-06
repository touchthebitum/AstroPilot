from dataclasses import dataclass

@dataclass(frozen=True)
class ProjectRiskContext:
    priority: float | None
    remaining_hours: float | None
    completion: float | None
    season_remaining_days: int | None
    favorable_nights: int | None
    pressure: float | None = 0.0
    required_nights: int | None = 0
    productive_hours_per_night: float | None = 4.0
    night_capacity_source: str = "profile"
    historical_nights: int | None = 0
