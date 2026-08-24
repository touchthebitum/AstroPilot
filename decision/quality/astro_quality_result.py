from dataclasses import dataclass, field


@dataclass(frozen=True)
class AstroQualityResult:
    score: float
    confidence: float
    limiting_factor: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)