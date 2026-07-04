from dataclasses import dataclass, field

@dataclass
class DecisionSummary:
    title: str
    confidence: float
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)