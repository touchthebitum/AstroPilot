from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioContext:
    """
    Describes the user's astrophotography portfolio.
    """

    active_projects: int

    total_remaining_hours: float

    highest_priority: int

    average_progress: float

    productive_hours_per_night: float | None = None
    observing_nights_per_week: float = 0.0

    night_capacity_source: str = "unknown"

    historical_nights: int | None = None
