from dataclasses import dataclass, field
from decision.night_productivity.night_window import NightWindow
from decision.night_productivity.night_slice import NightSlice


@dataclass(frozen=True)
class NightProductivityResult:
    astronomical_hours: float
    productive_hours: float
    confidence: float
    cloud_loss: float
    moon_loss: float
    altitude_loss: float
    weather_loss: float
    windows : list[NightWindow] = field(default_factory=list)
    timeline: list[NightSlice] = field(default_factory=list)
    display_start_hour: int = 22

