from __future__ import annotations

from typing import TYPE_CHECKING

from decision.models.candidate import Candidate
from decision.models.recommendation_reason import (
    RecommendationReason,
    RecommendationReasonCategory,
    RecommendationReasonScope,
)
from decision.weather.weather_trust_decision import WeatherTrustDecision

if TYPE_CHECKING:
    from decision.services.candidate_assessment import CandidateAssessment


_WINDOW_REASONS = frozenset({
    "selected_window_uncovered",
    "selected_window_coverage_unknown",
})
_WEATHER_REASONS = _WINDOW_REASONS | {
    "weather_provider_mismatch",
    "weather_location_mismatch",
    "weather_snapshot_missing",
    "weather_freshness_missing",
    "weather_not_fresh",
    "provider_reliability_context_missing",
    "provider_reliability_unavailable",
    "provider_report_scope_mismatch",
    "provider_context_not_evaluated",
    "invalid_weather_units",
}
_WEATHER_REASON_PREFIXES = (
    "provider_context_excluded:",
    "provider_comparison_excluded:",
    "provider_evidence_missing:",
    "provider_evidence_insufficient:",
    "maximum_absolute_error:",
)


def candidate_reasons(candidate: Candidate) -> tuple[RecommendationReason, ...]:
    """Preserve unclassified upstream messages without deriving their meaning."""
    if not isinstance(candidate, Candidate):
        raise TypeError("Expected a Candidate")
    return tuple(
        RecommendationReason(scope=RecommendationReasonScope.TARGET, message=message)
        for message in candidate.reasons
    )


def _weather_reasons(
    decision: WeatherTrustDecision,
    *,
    target_window_bound: bool,
) -> tuple[RecommendationReason, ...]:
    if not isinstance(decision, WeatherTrustDecision):
        raise TypeError("Expected a WeatherTrustDecision")
    return tuple(
        RecommendationReason(
            category=RecommendationReasonCategory.RELIABILITY,
            scope=(
                RecommendationReasonScope.TARGET
                if target_window_bound and code in _WINDOW_REASONS
                else RecommendationReasonScope.NIGHT
            ),
            basis=code,
            evidence_ref=decision,
        )
        for code in decision.reasons
        if code in _WEATHER_REASONS or any(
            code.startswith(prefix) and len(code) > len(prefix)
            for prefix in _WEATHER_REASON_PREFIXES
        )
    )


def weather_decision_reasons(
    decision: WeatherTrustDecision,
) -> tuple[RecommendationReason, ...]:
    """An unbound weather decision supplies shared context only."""
    return _weather_reasons(decision, target_window_bound=False)


def candidate_assessment_reasons(
    *,
    candidate: Candidate,
    assessment: CandidateAssessment | None,
) -> tuple[RecommendationReason, ...]:
    """The caller supplies the candidate and its own retained assessment together."""
    from decision.services.candidate_assessment import CandidateAssessment

    if not isinstance(candidate, Candidate):
        raise TypeError("Expected a Candidate identity")
    if assessment is None:
        return ()
    if not isinstance(assessment, CandidateAssessment):
        raise TypeError("Expected a CandidateAssessment")
    return _weather_reasons(assessment.weather_decision, target_window_bound=True)


def primary_window_reasons(
    *,
    candidate: Candidate,
    weather_decision: WeatherTrustDecision,
) -> tuple[RecommendationReason, ...]:
    """The caller explicitly binds the primary candidate to its own window decision."""
    if not isinstance(candidate, Candidate):
        raise TypeError("Expected a Candidate identity")
    return _weather_reasons(weather_decision, target_window_bound=True)
