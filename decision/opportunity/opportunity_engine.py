from decision.models.candidate import Candidate

from .action import Action
from .opportunity import Opportunity


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

        return Opportunity(
            action=Action.CONTINUE_PROJECT,
            candidate=best,
        )
