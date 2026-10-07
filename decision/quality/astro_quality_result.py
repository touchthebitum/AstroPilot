from dataclasses import dataclass, field


@dataclass(frozen=True)
class AstroQualityResult:
    """AQI on a 0–100 scale; score is diagnostic and non-comparable when partial.

    Only decision_score may be used for AQI decisions. Completeness is the known
    weight mass; confidence exposes the same coverage, not forecast reliability.
    """
    score: float
    confidence: float
    limiting_factor: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    # Legacy records lack proof of completeness and remain diagnostic.
    completeness: float = 0.0
    missing_metrics: tuple[str, ...] = ()
    decision_eligible: bool = False
    decision_score: float | None = None
    status: str = "insufficient_evidence"
