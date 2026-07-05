from dataclasses import dataclass

@dataclass
class WeatherForecast:

    hourly: list | None = None
    hourly_clouds: list | None = None
    hourly_humidity: list | None = None
    hourly_wind: list | None = None
    hourly_seeing: list | None = None
    hourly_moon_penalty: list | None = None
    hourly_temperature: list | None = None
    hourly_visibility: list | None = None
