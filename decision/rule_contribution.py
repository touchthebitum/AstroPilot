from dataclasses import dataclass
from typing import Optional


@dataclass
class RuleContribution:
    """
    Contribution d'une règle à la décision finale.
    """

    rule: str
    score: float
    confidence: float = 1.0
    reason: str = ""
    details: str = ""
    weight: float = 1.0
    recommendation: Optional[str] = None