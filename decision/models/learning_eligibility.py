"""Immutable determination of whether an execution can provide a learning signal."""

from dataclasses import dataclass
from enum import Enum


class LearningEligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class LearnableDimension(str, Enum):
    """Smallest dimension backed by an existing typed evidence category."""

    TECHNICAL = "technical"


class LearningEligibilityReasonCode(str, Enum):
    EXECUTION_NOT_STARTED = "execution_not_started"
    EXECUTION_IN_PROGRESS = "execution_in_progress"
    EXECUTION_UNCONFIRMED = "execution_unconfirmed"
    ASSESSMENT_INSUFFICIENT_EVIDENCE = "assessment_insufficient_evidence"
    NO_SUPPORTED_LEARNABLE_FINDING = "no_supported_learnable_finding"
    SUPPORTED_LEARNABLE_FINDING = "supported_learnable_finding"


@dataclass(frozen=True, slots=True)
class LearningEligibilityReason:
    code: LearningEligibilityReasonCode
    dimension: LearnableDimension | None = None
    finding_id: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, LearningEligibilityReasonCode):
            raise TypeError("Expected LearningEligibilityReasonCode")
        if self.code is LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING:
            if not isinstance(self.dimension, LearnableDimension):
                raise TypeError("supported_finding_dimension_required")
            if not isinstance(self.finding_id, str) or not self.finding_id.strip():
                raise ValueError("supported_finding_id_required")
            if not isinstance(self.evidence_ids, tuple) or not self.evidence_ids:
                raise ValueError("supported_finding_evidence_required")
            for evidence_id in self.evidence_ids:
                if not isinstance(evidence_id, str) or not evidence_id.strip():
                    raise ValueError("supported_finding_evidence_id_required")
            if len(set(self.evidence_ids)) != len(self.evidence_ids):
                raise ValueError("duplicate_supported_finding_evidence_id")
            return
        if self.dimension is not None or self.finding_id is not None or self.evidence_ids:
            raise ValueError("non_finding_reason_must_not_claim_finding_provenance")


@dataclass(frozen=True, slots=True)
class LearningEligibility:
    execution_id: str
    assessment_id: str | None
    status: LearningEligibilityStatus
    reasons: tuple[LearningEligibilityReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.execution_id, str) or not self.execution_id.strip():
            raise ValueError("execution_id_required")
        if self.assessment_id is not None and (
            not isinstance(self.assessment_id, str) or not self.assessment_id.strip()
        ):
            raise ValueError("assessment_id_invalid")
        if not isinstance(self.status, LearningEligibilityStatus):
            raise TypeError("Expected LearningEligibilityStatus")
        if not isinstance(self.reasons, tuple) or not self.reasons:
            raise ValueError("structured_reasons_required")
        if not all(type(reason) is LearningEligibilityReason for reason in self.reasons):
            raise TypeError("reasons_must_contain_learning_eligibility_reasons")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("duplicate_learning_eligibility_reason")

        codes = {reason.code for reason in self.reasons}
        execution_only_codes = {
            LearningEligibilityReasonCode.EXECUTION_NOT_STARTED,
            LearningEligibilityReasonCode.EXECUTION_IN_PROGRESS,
            LearningEligibilityReasonCode.EXECUTION_UNCONFIRMED,
        }
        if self.assessment_id is None:
            if (
                self.status is not LearningEligibilityStatus.NOT_ELIGIBLE
                or len(self.reasons) != 1
                or not codes.issubset(execution_only_codes)
            ):
                raise ValueError("assessment_id_required")
            return
        if codes & execution_only_codes:
            raise ValueError("assessment_result_must_not_use_execution_only_reason")
        if self.status is LearningEligibilityStatus.ELIGIBLE:
            if codes != {LearningEligibilityReasonCode.SUPPORTED_LEARNABLE_FINDING}:
                raise ValueError("eligible_requires_supported_finding")
        elif self.status is LearningEligibilityStatus.INSUFFICIENT_EVIDENCE:
            if self.reasons != (
                LearningEligibilityReason(
                    LearningEligibilityReasonCode.ASSESSMENT_INSUFFICIENT_EVIDENCE
                ),
            ):
                raise ValueError("insufficient_evidence_reason_required")
        elif codes != {LearningEligibilityReasonCode.NO_SUPPORTED_LEARNABLE_FINDING}:
            raise ValueError("not_eligible_reason_invalid")
