from dataclasses import dataclass
from typing import Optional


@dataclass
class ProjectEvaluation:
    """Évaluation complète d'un projet astrophotographique."""

    name: str

    astro_score: float = 0.0
    global_score: float = 0.0
    strategic_score: float = 0.0

    roi: float = 0.0
    priority: int = 0

    progress: float = 0.0
    remaining_hours: Optional[float] = None

    best_setup: str = ""
    setup_score: float = 0.0

    season_bonus: float = 0.0
    weather_bonus: float = 0.0
