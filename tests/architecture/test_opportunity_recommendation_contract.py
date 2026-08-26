from types import SimpleNamespace

from decision.recommendation.recommendation import Recommendation
from decision.recommendation.recommendation_engine import (
    RecommendationEngine,
)
from decision.services.opportunity_recommendation_service import (
    OpportunityRecommendationService,
)


def test_recommendation_engine_returns_none_without_opportunity():
    recommendation = RecommendationEngine().recommend(opportunity=None)

    assert recommendation is None


def test_recommendation_engine_preserves_opportunity_identity():
    opportunity = SimpleNamespace(candidate="M31")

    recommendation = RecommendationEngine().recommend(
        opportunity=opportunity,
    )

    assert recommendation == Recommendation(
        opportunity=opportunity,
        confidence=1.0,
    )
    assert recommendation.opportunity is opportunity


def test_service_passes_candidates_and_opportunity_without_copying():
    candidates = [
        SimpleNamespace(name="M31"),
        SimpleNamespace(name="M42"),
    ]
    opportunity = SimpleNamespace(candidate=candidates[0])
    captured = {}

    class FakeOpportunityEngine:
        def evaluate(self, *, candidates):
            captured["candidates"] = candidates
            return opportunity

    class FakeRecommendationEngine:
        def recommend(self, *, opportunity):
            captured["opportunity"] = opportunity
            return SimpleNamespace(opportunity=opportunity)

    service = OpportunityRecommendationService(
        opportunity_engine=FakeOpportunityEngine(),
        recommendation_engine=FakeRecommendationEngine(),
    )

    recommendation = service.build(candidates=candidates)

    assert captured["candidates"] is candidates
    assert captured["opportunity"] is opportunity
    assert recommendation.opportunity is opportunity


def test_service_propagates_absence_of_opportunity_to_recommender():
    captured = {}

    class EmptyOpportunityEngine:
        def evaluate(self, *, candidates):
            return None

    class RecordingRecommendationEngine:
        def recommend(self, *, opportunity):
            captured["opportunity"] = opportunity
            return None

    service = OpportunityRecommendationService(
        opportunity_engine=EmptyOpportunityEngine(),
        recommendation_engine=RecordingRecommendationEngine(),
    )

    assert service.build(candidates=[]) is None
    assert captured["opportunity"] is None
