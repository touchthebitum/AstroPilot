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

    productive_hours_per_night: float = 4.0

    night_capacity_source: str = "profile"

    historical_nights: int = 0
