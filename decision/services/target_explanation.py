from collections.abc import Sequence
from dataclasses import dataclass

from decision.services.tonight_response import (
    AlternativeReasonResponse,
    PrimaryRecommendationReasonResponse,
    TargetDecisionStatus,
    TargetExplanationResponse,
)


TargetReasonResponse = (
    PrimaryRecommendationReasonResponse | AlternativeReasonResponse
)


@dataclass(frozen=True)
class TargetExplanation:
    catalog_key: str
    target_decision_status: TargetDecisionStatus
    reasons: tuple[TargetReasonResponse, ...]

    def __post_init__(self):
        object.__setattr__(self, "reasons", tuple(self.reasons))


def build_target_explanations(
    *,
    primary: tuple[
        str,
        Sequence[PrimaryRecommendationReasonResponse],
    ] | None,
    alternatives: Sequence[
        tuple[str, Sequence[AlternativeReasonResponse]]
    ],
) -> tuple[TargetExplanation, ...]:
    explanations = []
    if primary is not None:
        catalog_key, reasons = primary
        explanations.append(TargetExplanation(
            catalog_key=catalog_key,
            target_decision_status=TargetDecisionStatus.RECOMMENDED,
            reasons=tuple(reasons),
        ))
    explanations.extend(
        TargetExplanation(
            catalog_key=catalog_key,
            target_decision_status=TargetDecisionStatus.VIABLE,
            reasons=tuple(reasons),
        )
        for catalog_key, reasons in alternatives
    )
    return tuple(explanations)


def target_explanation_responses(
    explanations: Sequence[TargetExplanation],
) -> tuple[TargetExplanationResponse, ...]:
    return tuple(
        TargetExplanationResponse(
            catalog_key=explanation.catalog_key,
            target_decision_status=explanation.target_decision_status,
            reasons=explanation.reasons,
        )
        for explanation in explanations
    )
