from collections.abc import Sequence

from decision.models.recommendation_comparison import RecommendationComparison
from decision.models.recommendation_reason import RecommendationReason
from decision.services.recommendation_comparison_builder import (
    compare_recommendation_reasons,
)
from decision.services.tonight_response import (
    RecommendationComparisonResponse,
    RecommendationReasonResponse,
)


def _reason_responses(
    reasons: Sequence[RecommendationReason],
) -> tuple[RecommendationReasonResponse, ...]:
    return tuple(
        RecommendationReasonResponse(
            category=reason.category,
            scope=reason.scope,
            direction=reason.direction,
            importance=reason.importance,
            basis=reason.basis,
            message=reason.message,
            evidence_ref=reason.evidence_ref,
        )
        for reason in reasons
    )


def comparison_response(
    comparison: RecommendationComparison,
) -> RecommendationComparisonResponse:
    return RecommendationComparisonResponse(
        primary_catalog_key=comparison.primary_catalog_key,
        alternative_catalog_key=comparison.alternative_catalog_key,
        primary_only_reasons=_reason_responses(comparison.primary_only_reasons),
        alternative_only_reasons=_reason_responses(comparison.alternative_only_reasons),
        shared_reasons=_reason_responses(comparison.shared_reasons),
    )


def build_alternative_comparisons(
    *,
    primary_catalog_key: str,
    primary_reasons: Sequence[RecommendationReason],
    alternatives: Sequence[tuple[str, Sequence[RecommendationReason]]],
) -> tuple[RecommendationComparisonResponse, ...]:
    """The caller supplies only exposed alternatives, in their existing order."""
    return tuple(
        comparison_response(
            compare_recommendation_reasons(
                primary_catalog_key=primary_catalog_key,
                alternative_catalog_key=catalog_key,
                primary_reasons=primary_reasons,
                alternative_reasons=reasons,
            )
        )
        for catalog_key, reasons in alternatives
    )
