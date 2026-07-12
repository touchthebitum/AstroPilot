from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisResult:
    """
    Contrat commun de toutes les analyses AstroPilot.
    """

    analysis_name: str
    conclusion: str
    confidence: float
