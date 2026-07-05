from dataclasses import dataclass, field
from dataclasses import dataclass, field 
from typing import Any


@dataclass(frozen=True)
class RiskReport:
    level: str
    score: int
    explanation: list[str] = field(default_factory=list)
    context: Any = None