from dataclasses import dataclass


@dataclass(frozen=True)
class NightWindow:
    start_hour: float
    end_hour: float

    productivity: float          # 0.0 → 1.0

    altitude: float
    cloud_cover: float
    moon_penalty: float
    seeing: float

    productive: bool

    reason: str