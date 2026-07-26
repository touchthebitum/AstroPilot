from dataclasses import dataclass
from datetime import datetime

from decision.weather.weather_forecast import WeatherForecast


@dataclass(frozen=True)
class MissionInput:
    window_start: datetime | None
    window_end: datetime | None
    astronomical_hours: float | None
    weather: WeatherForecast | None
    moon_penalty: float | None
    recommended_hours: float
    expected_gain: float
