from decision.models.recommendation_reason import RecommendationReason
from decision.models.recommendation_reason_presentation import (
    RecommendationReasonPresentation,
)


_PRESENTATION_KEYS = {
    "selected_window_uncovered": "selected_window_uncovered",
    "selected_window_coverage_unknown": "selected_window_coverage_unknown",
    "weather_provider_mismatch": "weather_provider_mismatch",
    "weather_location_mismatch": "weather_location_mismatch",
    "weather_snapshot_missing": "weather_snapshot_missing",
    "weather_freshness_missing": "weather_freshness_missing",
    "weather_not_fresh": "weather_not_fresh",
    "provider_reliability_context_missing": (
        "provider_reliability_context_missing"
    ),
    "provider_reliability_unavailable": "provider_reliability_unavailable",
    "provider_report_scope_mismatch": "provider_report_scope_mismatch",
    "provider_context_not_evaluated": "provider_context_not_evaluated",
}


def recommendation_reason_presentation(
    reason: RecommendationReason,
) -> RecommendationReasonPresentation | None:
    """Map verified machine bases without interpreting legacy reason text."""
    if not isinstance(reason, RecommendationReason):
        raise TypeError("Expected a RecommendationReason")
    if reason.basis is None:
        return None
    presentation_key = _PRESENTATION_KEYS.get(reason.basis)
    if presentation_key is None:
        return None
    return RecommendationReasonPresentation(
        basis=reason.basis,
        presentation_key=presentation_key,
    )
