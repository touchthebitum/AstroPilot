from decision.opportunity.opportunity import Opportunity

from .recommendation import Recommendation


class RecommendationEngine:

    def recommend(
        self,
        *,
        opportunity: Opportunity | None,
    ) -> Recommendation | None:

        if opportunity is None:
            return None

        return Recommendation(
            opportunity=opportunity,
            confidence=1.0,
        )