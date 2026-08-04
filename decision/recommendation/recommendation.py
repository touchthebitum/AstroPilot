from dataclasses import dataclass

from decision.opportunity.opportunity import Opportunity


@dataclass(slots=True)
class Recommendation:
    opportunity: Opportunity
    confidence: float