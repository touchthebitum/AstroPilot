from dataclasses import dataclass, field
from typing import Any


@dataclass
class EngineResult:
    """
    Standard result returned by every AstroPilot engine.
    """

    score: float

    confidence: float = 1.0

    explanation: str = ""

    recommendation: str = ""

    limiting_factor: str | None = None

    metrics: dict[str, Any] = field(default_factory=dict)