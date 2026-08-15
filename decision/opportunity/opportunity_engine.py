from decision.models.candidate import Candidate

from .action import Action
from .opportunity import Opportunity
from .opportunity_reason_builder import OpportunityReasonBuilder


class OpportunityEngine:

    def evaluate(
        self,
        *,
        candidates: list[Candidate],
    ) -> Opportunity | None:

        if not candidates:
            return None

        best = max(
            candidates,
            key=lambda candidate: candidate.decision_score,
        )

        action = (
            Action.CONTINUE_PROJECT
            if best.acquired_hours > 0
            else Action.START_PROJECT
        )

        return Opportunity(
            action=action,
            candidate=best,
            reasons=OpportunityReasonBuilder.build(
                candidate=best,
            ),
        )
