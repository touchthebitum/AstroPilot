from dataclasses import dataclass

@dataclass(frozen=True)
class ProjectRiskContext:
    priority: float
    remaining_hours: float
    completion: float
    season_remaining_days: int
    favorable_nights: int