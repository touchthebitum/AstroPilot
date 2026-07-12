from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnalysisResult:
    analysis_name: str
    conclusion: str
    confidence: float
    data: dict[str, Any] = field(default_factory=dict)
