from __future__ import annotations

from decision.models.candidate_rejection import CandidateRejection
from decision.services.tonight_response import TonightRejectedTargetResponse


def map_rejected_targets(
    rejections: tuple[CandidateRejection, ...],
) -> tuple[TonightRejectedTargetResponse, ...]:
    """Expose explicit rejections in source order without assessing candidates."""
    entries = []
    for rejection in rejections:
        if not isinstance(rejection, CandidateRejection):
            raise TypeError("Expected a CandidateRejection record")
        entries.append(
            TonightRejectedTargetResponse(
                target=rejection.target,
                catalog_key=rejection.catalog_key,
                provenance=rejection.provenance,
                basis=rejection.basis,
                evaluation_score=rejection.evaluation_score,
            )
        )
    return tuple(entries)
