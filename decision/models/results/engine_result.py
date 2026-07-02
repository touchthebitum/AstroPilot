from dataclasses import dataclass, field
from typing import Any


@dataclass
class EngineResult:
    """
    Standard interface returned by every AstroPilot Engine.
    """

    score: float

    confidence: float = 1.0

    explanation: str = ""

    recommendation: str = ""

    limiting_factor: str | None = None

    metrics: dict[str, Any] = field(default_factory=dict)
