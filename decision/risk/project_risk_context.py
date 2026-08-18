from dataclasses import dataclass

@dataclass(frozen=True)
class ProjectRiskContext:
    priority: float
    remaining_hours: float
    completion: float
    season_remaining_days: int | None
    favorable_nights: int | None
    pressure: float = 0.0
    required_nights: int = 0
