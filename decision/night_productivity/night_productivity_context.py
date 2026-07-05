from dataclasses import dataclass


@dataclass(frozen=True)
class NightProductivityContext:

    astronomical_hours: float

    cloud_cover: float
    moon_penalty: float

    altitude_score: float

    humidity: float
    wind: float

    seeing: float

    hourly_clouds: list | None = None
    hourly_humidity: list | None = None
    hourly_wind: list | None = None
    hourly_seeing: list | None = None
    hourly_moon_penalty: list | None = None
    weather: object | None = None