from decision.models.candidate import Candidate
from decision.opportunity.opportunity_engine import OpportunityEngine
from decision.recommendation.recommendation import Recommendation
from decision.recommendation.recommendation_engine import (
    RecommendationEngine,
)


class OpportunityRecommendationService:

    def __init__(
        self,
        *,
        opportunity_engine: OpportunityEngine,
        recommendation_engine: RecommendationEngine,
    ):
        self.opportunity_engine = opportunity_engine
        self.recommendation_engine = recommendation_engine

    def build(
        self,
        *,
        candidates: list[Candidate],
    ) -> Recommendation | None:
        opportunity = self.opportunity_engine.evaluate(
            candidates=candidates,
        )

        return self.recommendation_engine.recommend(
            opportunity=opportunity,
        )
