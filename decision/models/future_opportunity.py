from dataclasses import dataclass
from decision.portfolio.historical_night_capacity_estimator import NightCapacityEstimate


@dataclass(frozen=True)
class FutureOpportunity:
    good_nights: int
    risk: str
    weather_ratio: float
    needed_nights: int
    # Forecast/model evidence, never a certificate of Tonight availability.
    opportunity_ratio: float

    night_capacity: NightCapacityEstimate | None = None
