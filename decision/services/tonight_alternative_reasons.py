from collections.abc import Sequence

from decision.models.recommendation_reason import RecommendationReason
from decision.models.recommendation_reason_rendering import PresentationDepth
from decision.services.recommendation_reason_presentation import (
    recommendation_reason_presentation,
)
from decision.services.recommendation_reason_renderer import (
    render_recommendation_reason,
)
from decision.services.tonight_response import (
    AlternativeReasonResponse,
    RecommendationReasonRenderingResponse,
)


def _rendered_reason_response(
    reason: RecommendationReason,
) -> RecommendationReasonRenderingResponse | None:
    presentation = recommendation_reason_presentation(reason)
    if presentation is None:
        return None
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
        return None
    return RecommendationReasonRenderingResponse(
        presentation_key=presentation.presentation_key,
        classic_text=classic.text,
        pro_text=pro.text,
    )


def alternative_reason_responses(
    reasons: Sequence[RecommendationReason],
) -> tuple[AlternativeReasonResponse, ...]:
    return tuple(
        AlternativeReasonResponse(
            scope=reason.scope,
            category=reason.category,
            direction=reason.direction,
            importance=reason.importance,
            basis=reason.basis,
            message=reason.message,
            rendered=_rendered_reason_response(reason),
        )
        for reason in reasons
    )
