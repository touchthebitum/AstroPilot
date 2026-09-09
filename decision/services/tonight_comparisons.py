from collections.abc import Sequence

from decision.models.recommendation_comparison import RecommendationComparison
from decision.models.recommendation_reason import RecommendationReason
from decision.models.recommendation_reason_rendering import PresentationDepth
from decision.services.recommendation_comparison_builder import (
    compare_recommendation_reasons,
)
from decision.services.recommendation_reason_presentation import (
    recommendation_reason_presentation,
)
from decision.services.recommendation_reason_renderer import (
    render_recommendation_reason,
)
from decision.services.tonight_response import (
    RecommendationComparisonResponse,
    RecommendationReasonResponse,
    RecommendationReasonRenderingResponse,
)


def _rendered_reason_responses(
    reason: RecommendationReason,
) -> tuple[RecommendationReasonRenderingResponse, ...]:
    presentation = recommendation_reason_presentation(reason)
    if presentation is None:
        return ()
    try:
        classic = render_recommendation_reason(
            presentation,
            depth=PresentationDepth.CLASSIC,
        )
        pro = render_recommendation_reason(
            presentation,
            depth=PresentationDepth.PRO,
        )
    except ValueError:
        return ()
    return (
        RecommendationReasonRenderingResponse(
            presentation_key=presentation.presentation_key,
            classic_text=classic.text,
            pro_text=pro.text,
        ),
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
            rendered_reasons=_rendered_reason_responses(reason),
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
