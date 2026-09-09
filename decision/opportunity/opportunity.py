from dataclasses import dataclass, field

from decision.models.candidate import Candidate
from decision.models.recommendation_reason import RecommendationReason

from .action import Action
from .opportunity_reason import OpportunityReason


@dataclass(slots=True)
class Opportunity:
    action: Action
    candidate: Candidate
    reasons: list[OpportunityReason] = field(default_factory=list)
    shortlist_entries: tuple[Candidate, ...] = ()

    @property
    def structured_reasons(self) -> tuple[RecommendationReason, ...]:
        from decision.services.recommendation_reason_builder import candidate_reasons

        return candidate_reasons(self.candidate)
