from decision.models.candidate import Candidate

from .opportunity_reason import OpportunityReason


class OpportunityReasonBuilder:

    @staticmethod
    def build(
        *,
        candidate: Candidate,
    ) -> list[OpportunityReason]:
        return [
            OpportunityReason(
                title="Facteur décisionnel",
                message=reason,
            )
            for reason in candidate.reasons
        ]
