from dataclasses import dataclass


@dataclass
class NightSlice:
    start_hour: float
    end_hour: float

    target_altitude: float
    target_azimuth: float

    moon_altitude: float
    moon_separation: float

    cloud_cover: float
    humidity: float
    wind: float
    seeing: float
    sqm: float
    
    astro_score: float
    conditions_score: float
    productivity_score: float