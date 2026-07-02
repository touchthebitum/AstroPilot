from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherContext:
    """
    Describes weather conditions available for the decision.
    """

    cloud_cover: float
    humidity: float
    wind_speed_kmh: float

    seeing_arcsec: float | None = None
    transparency: float | None = None
    temperature_c: float | None = None

    forecast_confidence: float | None = None