from dataclasses import dataclass, field

from decision.models.candidate import Candidate

from .action import Action
from .opportunity_reason import OpportunityReason


@dataclass(slots=True)
class Opportunity:
    action: Action
    candidate: Candidate
    reasons: list[OpportunityReason] = field(default_factory=list)
