from collections import defaultdict, deque
from collections.abc import Sequence

from decision.models.recommendation_comparison import RecommendationComparison
from decision.models.recommendation_reason import (
    RecommendationReason,
    RecommendationReasonCategory,
    RecommendationReasonScope,
)


_ReasonIdentity = tuple[
    RecommendationReasonScope, RecommendationReasonCategory | None, str
]


def _machine_identity(reason: RecommendationReason) -> _ReasonIdentity | None:
    if not isinstance(reason, RecommendationReason):
        raise TypeError("Expected a RecommendationReason")
    if reason.basis is None:
        return None
    return reason.scope, reason.category, reason.basis


def compare_recommendation_reasons(
    *,
    primary_catalog_key: str,
    alternative_catalog_key: str,
    primary_reasons: Sequence[RecommendationReason],
    alternative_reasons: Sequence[RecommendationReason],
) -> RecommendationComparison:
    """Compare existing reasons without interpreting their meaning.

    Shared entries retain the original primary objects in primary order.
    Duplicate identities match one occurrence at a time, in source order;
    unmatched occurrences remain on their respective side.
    """
    primary = tuple(primary_reasons)
    alternative = tuple(alternative_reasons)
    available: dict[_ReasonIdentity, deque[int]] = defaultdict(deque)
    for index, reason in enumerate(alternative):
        identity = _machine_identity(reason)
        if identity is not None:
            available[identity].append(index)

    matched_alternative = set()
    primary_only = []
    shared = []
    for reason in primary:
        identity = _machine_identity(reason)
        matches = available.get(identity) if identity is not None else None
        if matches:
            matched_alternative.add(matches.popleft())
            shared.append(reason)
        else:
            primary_only.append(reason)

    return RecommendationComparison(
        primary_catalog_key=primary_catalog_key,
        alternative_catalog_key=alternative_catalog_key,
        primary_only_reasons=tuple(primary_only),
        alternative_only_reasons=tuple(
            reason
            for index, reason in enumerate(alternative)
            if index not in matched_alternative
        ),
        shared_reasons=tuple(shared),
    )
