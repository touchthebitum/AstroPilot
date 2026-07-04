from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskReport:
    level: str
    score: int
    explanation: list[str] = field(default_factory=list)