from dataclasses import dataclass


@dataclass
class NightSlice:
    start_hour: float
    end_hour: float

    altitude: float
    cloud_cover: float
    humidity: float
    wind: float
    seeing: float

    moon_penalty: float

    productivity: float = 0.0