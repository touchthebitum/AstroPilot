"""Immutable provenance-only candidate signal for a future learning pipeline."""

from dataclasses import dataclass
from datetime import datetime

from decision.models.learning_eligibility import (
    LearnableDimension,
    LearningEligibility,
    LearningEligibilityReasonCode,
    LearningEligibilityStatus,
)


@dataclass(frozen=True, slots=True)
class LearningSignal:
    signal_id: str
    execution_id: str
    assessment_id: str
    eligibility: LearningEligibility
    dimension: LearnableDimension
    evidence_ids: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("signal_id", "execution_id", "assessment_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if type(self.eligibility) is not LearningEligibility:
            raise TypeError("eligibility_must_be_learning_eligibility")
        if self.eligibility.status is not LearningEligibilityStatus.ELIGIBLE:
            raise ValueError("eligible_learning_eligibility_required")
        if self.execution_id != self.eligibility.execution_id:
            raise ValueError("eligibility_execution_mismatch")
        if self.assessment_id != self.eligibility.assessment_id:
            raise ValueError("eligibility_assessment_mismatch")
        if not isinstance(self.dimension, LearnableDimension):
            raise TypeError("Expected LearnableDimension")
        if not isinstance(self.evidence_ids, tuple):
            raise TypeError("evidence_ids_must_be_tuple")
        if not self.evidence_ids:
            raise ValueError("evidence_required")
        for evidence_id in self.evidence_ids:
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                raise ValueError("evidence_id_required")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate_evidence_id")
        matching_reasons = tuple(
            reason
            for reason in self.eligibility.reasons
            if reason.code is LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING
            and reason.dimension is self.dimension
            and reason.evidence_ids == self.evidence_ids
        )
        if len(matching_reasons) != 1:
            raise ValueError("dimension_or_evidence_not_explicitly_eligible")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at_must_be_datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at_timezone_required")
