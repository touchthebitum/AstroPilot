from __future__ import annotations

from dataclasses import dataclass

from decision.models.candidate import CandidateProvenance
from decision.weather.weather_trust_decision import (
    WeatherDecisionAdmissibility,
    WeatherEvidenceQuality,
    WeatherTrustDecision,
)


@dataclass(frozen=True)
class TargetEvidenceInsufficiency:
    target: str
    catalog_key: str
    provenance: CandidateProvenance
    weather_decision: WeatherTrustDecision

    def __post_init__(self):
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.target, self.catalog_key)
        ):
            raise ValueError("target_evidence_identity_required")
        if not isinstance(self.provenance, CandidateProvenance):
            raise TypeError("Expected CandidateProvenance")
        if not isinstance(self.weather_decision, WeatherTrustDecision):
            raise TypeError("Expected a WeatherTrustDecision")
        if (
            self.weather_decision.evidence_quality
            is not WeatherEvidenceQuality.INSUFFICIENT
            or self.weather_decision.admissibility
            is not WeatherDecisionAdmissibility.REFUSED
        ):
            raise ValueError("target_evidence_insufficient_refusal_required")
