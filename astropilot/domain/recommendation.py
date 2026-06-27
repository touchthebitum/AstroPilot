from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Recommendation:
    """
    Représente une décision complète produite par AstroPilot.

    Une recommandation ne contient pas seulement une cible.
    Elle contient aussi :
    - pourquoi cette cible est choisie
    - le niveau de confiance
    - les alternatives rejetées
    - les avertissements
    - les hypothèses
    """

    target: str
    confidence: float

    setup: Optional[str] = None
    filter: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    rejected_targets: List[Dict[str, Any]] = field(default_factory=list)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    expected_gain: Optional[float] = None
    postponement_risk: Optional[float] = None
    score: Optional[float] = None

    def add_reason(self, reason: str):
        self.reasons.append(reason)

    def add_warning(self, warning: str):
        self.warnings.append(warning)

    def add_assumption(self, assumption: str):
        self.assumptions.append(assumption)

    def to_dict(self):
        return {
            "target": self.target,
            "confidence": self.confidence,
            "setup": self.setup,
            "filter": self.filter,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "assumptions": self.assumptions,
            "rejected_targets": self.rejected_targets,
            "alternatives": self.alternatives,
            "expected_gain": self.expected_gain,
            "postponement_risk": self.postponement_risk,
            "score": self.score,
        }
