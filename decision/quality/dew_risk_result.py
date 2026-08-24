from dataclasses import dataclass


@dataclass(frozen=True)
class DewRiskResult:
    dew_point_c: float
    spread_c: float
    risk: str
    score: float