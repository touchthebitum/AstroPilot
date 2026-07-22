from dataclasses import dataclass


@dataclass(frozen=True)
class FutureOpportunity:
    good_nights: int
    risk: str
    weather_ratio: float
    needed_nights: int
    opportunity_ratio: float
