from __future__ import annotations

from decision.models.candidate import Candidate
from decision.models.target_evidence_insufficiency import TargetEvidenceInsufficiency
from decision.services.candidate_assessment import CandidateAssessment
from decision.services.tonight_response import TonightInsufficientEvidenceTargetResponse
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


def _qualify_bound_decision(
    candidate: Candidate,
    weather_decision: WeatherTrustDecision | None,
) -> TargetEvidenceInsufficiency | None:
    if not isinstance(candidate, Candidate):
        raise TypeError("Expected a Candidate identity")
    if weather_decision is None:
        return None
    if not isinstance(weather_decision, WeatherTrustDecision):
        raise TypeError("Expected a WeatherTrustDecision")
    if (
        weather_decision.evidence_quality is not WeatherEvidenceQuality.INSUFFICIENT
        or weather_decision.admissibility is not WeatherDecisionAdmissibility.REFUSED
    ):
        return None
    return TargetEvidenceInsufficiency(
        target=candidate.name,
        catalog_key=candidate.catalog_key,
        provenance=candidate.provenance,
        weather_decision=weather_decision,
    )


def qualify_candidate_evidence_insufficiency(
    *,
    candidate: Candidate,
    assessment: CandidateAssessment | None,
) -> TargetEvidenceInsufficiency | None:
    """Qualify an assessment explicitly associated with this candidate by its caller."""
    if assessment is not None and not isinstance(assessment, CandidateAssessment):
        raise TypeError("Expected a CandidateAssessment")
    return _qualify_bound_decision(
        candidate,
        assessment.weather_decision if assessment is not None else None,
    )


def qualify_primary_evidence_insufficiency(
    *,
    candidate: Candidate,
    weather_decision: WeatherTrustDecision | None,
) -> TargetEvidenceInsufficiency | None:
    """Bind only the primary candidate to its own existing primary-window decision."""
    return _qualify_bound_decision(candidate, weather_decision)


def map_target_evidence_insufficiencies(
    records: tuple[TargetEvidenceInsufficiency, ...],
) -> tuple[TonightInsufficientEvidenceTargetResponse, ...]:
    entries = []
    for record in records:
        if not isinstance(record, TargetEvidenceInsufficiency):
            raise TypeError("Expected a TargetEvidenceInsufficiency record")
        entries.append(
            TonightInsufficientEvidenceTargetResponse(
                target=record.target,
                catalog_key=record.catalog_key,
                provenance=record.provenance,
                weather_decision=record.weather_decision,
            )
        )
    return tuple(entries)
