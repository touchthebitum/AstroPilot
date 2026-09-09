from dataclasses import FrozenInstanceError, asdict, fields

import pytest

from decision.models.candidate import Candidate
from decision.opportunity.opportunity_engine import OpportunityEngine
from decision.recommendation.recommendation import Recommendation
from decision.services.candidate_assessment import CandidateAssessment
from decision.services.tonight_application_service import TonightResult
from decision.services.tonight_response import TonightResponse
from decision.weather.provider_reliability import WeatherLocation
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherDecisionContext,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
    WeatherTrustDecisionEvaluator,
    WeatherTrustEvidence,
)


def candidate(reasons=(), *, score=100, acquired_hours=0):
    return Candidate(
        name="M31", catalog_key="M31", priority=0, astro_score=0,
        final_score=0, decision_score=score, portfolio_score=0,
        global_score=0, setup_score=0, best_setup=None, closure_bonus=0,
        acquired_hours=acquired_hours, reasons=list(reasons),
    )


def test_semantic_reason_is_immutable_nullable_and_has_no_presentation_title():
    from decision.models.recommendation_reason import (
        RecommendationReason,
        RecommendationReasonScope,
    )

    reason = RecommendationReason(scope=RecommendationReasonScope.TARGET)
    assert [field.name for field in fields(reason)] == [
        "category", "scope", "direction", "importance", "basis", "message",
        "evidence_ref",
    ]
    assert all(
        getattr(reason, name) is None
        for name in ("category", "direction", "importance", "basis", "message", "evidence_ref")
    )
    with pytest.raises(FrozenInstanceError):
        reason.message = "changed"
    with pytest.raises(TypeError):
        RecommendationReason(scope="arbitrary")


@pytest.mark.parametrize("messages", [(), ("Excellent rendement",), (
    "Excellent rendement", "Projet prioritaire", "Excellent rendement", "",
)])
def test_candidate_messages_are_preserved_without_inferred_classification(messages):
    from decision.models.recommendation_reason import RecommendationReasonScope

    source = candidate(messages)
    opportunity = OpportunityEngine().evaluate(candidates=[source])
    recommendation = Recommendation(opportunity=opportunity, confidence=None)
    original = list(source.reasons)
    legacy = asdict(opportunity)
    result = TonightResult(night=None, recommendation=recommendation, mission=None)
    payload = TonightResponse.from_result(result).to_dict()

    reasons = recommendation.opportunity.structured_reasons
    assert isinstance(reasons, tuple)
    assert [reason.message for reason in reasons] == list(messages)
    for reason in reasons:
        assert reason.scope is RecommendationReasonScope.TARGET
        assert reason.category is reason.direction is reason.importance is None
        assert reason.basis is reason.evidence_ref is None
    assert [reason.message for reason in opportunity.reasons] == list(messages)
    assert all(reason.title == "Facteur décisionnel" for reason in opportunity.reasons)
    assert source.reasons == original
    assert asdict(opportunity) == legacy
    assert "structured_reasons" not in legacy
    assert TonightResponse.from_result(result).to_dict() == payload


@pytest.mark.parametrize("acquired_hours", [None, 0, 2.5])
def test_selection_action_and_scores_do_not_generate_semantic_reasons(acquired_hours):
    winner = candidate(score=100, acquired_hours=acquired_hours)
    loser = candidate(("Projet prioritaire",), score=10)
    opportunity = OpportunityEngine().evaluate(candidates=[loser, winner])

    assert opportunity.candidate is winner
    assert opportunity.shortlist_entries == (loser,)
    assert opportunity.structured_reasons == ()


@pytest.mark.parametrize("coverage", [False, None])
def test_weather_evaluator_reasons_are_preserved_with_shared_scope(coverage):
    from decision.models.recommendation_reason import (
        RecommendationReasonCategory,
        RecommendationReasonScope,
    )

    decision = WeatherTrustDecisionEvaluator.evaluate(
        WeatherTrustEvidence(
            snapshot=None, freshness=None, selected_window_covered=coverage,
        ),
        context=WeatherDecisionContext(
            provider_id="Open-Meteo", decision_location=WeatherLocation(46.75, 6.55),
        ),
    )
    original = asdict(decision)
    reason_codes = decision.reasons
    reasons = decision.structured_reasons
    assert [reason.basis for reason in reasons] == list(reason_codes)
    for reason in reasons:
        assert reason.category is RecommendationReasonCategory.RELIABILITY
        assert reason.scope is RecommendationReasonScope.NIGHT
        assert reason.message is reason.direction is reason.importance is None
        assert reason.evidence_ref is decision
    assert decision.reasons is reason_codes
    assert asdict(decision) == original
    assert set(original) == {"evidence_quality", "admissibility", "reasons"}


@pytest.mark.parametrize("code", [
    "weather_provider_mismatch", "weather_location_mismatch",
    "weather_not_fresh", "provider_reliability_context_missing",
    "provider_reliability_unavailable", "provider_report_scope_mismatch",
    "provider_context_not_evaluated", "invalid_weather_units",
    "provider_evidence_missing:cloud_cover_percent",
    "provider_evidence_insufficient:cloud_cover_percent",
    "maximum_absolute_error:cloud_cover_percent:5",
])
def test_existing_weather_codes_keep_their_basis_without_new_text_or_priorities(code):
    decision = WeatherTrustDecision(
        WeatherEvidenceQuality.INSUFFICIENT,
        WeatherDecisionAdmissibility.CAUTION,
        (code, code),
    )
    reasons = decision.structured_reasons
    assert [reason.basis for reason in reasons] == [code, code]
    assert all(reason.message is reason.direction is reason.importance is None for reason in reasons)


@pytest.mark.parametrize("code", [
    "selected_window_uncovered", "selected_window_coverage_unknown",
])
def test_only_explicitly_bound_window_reasons_receive_target_scope(code):
    from decision.models.recommendation_reason import RecommendationReasonScope
    from decision.services.recommendation_reason_builder import (
        candidate_assessment_reasons,
        primary_window_reasons,
    )

    source = candidate()
    decision = WeatherTrustDecision(
        WeatherEvidenceQuality.INSUFFICIENT,
        WeatherDecisionAdmissibility.REFUSED,
        ("weather_freshness_missing", code, "provider_reliability_unavailable"),
    )
    assessment = CandidateAssessment(productive_window=None, weather_decision=decision)
    bound_collections = (
        candidate_assessment_reasons(candidate=source, assessment=assessment),
        primary_window_reasons(candidate=source, weather_decision=decision),
    )
    for reasons in bound_collections:
        assert [reason.scope for reason in reasons] == [
            RecommendationReasonScope.NIGHT,
            RecommendationReasonScope.TARGET,
            RecommendationReasonScope.NIGHT,
        ]
        assert [reason.basis for reason in reasons] == list(decision.reasons)
        assert all(reason.evidence_ref is decision for reason in reasons)
    assert all(reason.scope is RecommendationReasonScope.NIGHT for reason in decision.structured_reasons)
    assert candidate_assessment_reasons(candidate=source, assessment=None) == ()
    with pytest.raises(TypeError):
        candidate_assessment_reasons(candidate=None, assessment=assessment)
    with pytest.raises(TypeError):
        primary_window_reasons(candidate=None, weather_decision=decision)


def test_unknown_codes_and_presentation_strings_do_not_become_semantic_weather_reasons():
    decision = WeatherTrustDecision(
        WeatherEvidenceQuality.INSUFFICIENT,
        WeatherDecisionAdmissibility.REFUSED,
        ("Mission non confirmée", "unverified_code", "Facteur décisionnel"),
    )
    assert decision.structured_reasons == ()
    assert decision.reasons == (
        "Mission non confirmée", "unverified_code", "Facteur décisionnel",
    )
