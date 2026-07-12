from dataclasses import dataclass
from typing import Any


@dataclass
class AnalysisContext:
    target: str
    weather: Any = None
    productivity: Any = None
    risk: Any = None