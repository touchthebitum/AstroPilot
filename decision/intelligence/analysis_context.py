from dataclasses import dataclass
from typing import Any
from datetime import datetime


@dataclass
class AnalysisContext:
    target: str

    weather: Any = None
    productivity: Any = None
    risk: Any = None

    latitude: float | None = None
    longitude: float | None = None
    observation_time: datetime | None = None
