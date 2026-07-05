from dataclasses import dataclass

@dataclass(frozen=True)
class ProductivityResult:
    productive_hours: float
    efficiency: float
    lost_cloud_hours: float
    lost_moon_hours: float
    lost_altitude_hours: float
    required_nights: int