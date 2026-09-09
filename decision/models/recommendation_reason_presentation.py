from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecommendationReasonPresentation:
    basis: str
    presentation_key: str
