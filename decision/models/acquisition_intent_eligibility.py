"""First-class eligibility result for one acquisition intent."""

from dataclasses import dataclass
from enum import Enum


class AcquisitionIntentEligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AcquisitionIntentEligibilityReason(str, Enum):
    INTENT_NOT_IN_IMAGING_FIELD = "intent_not_in_imaging_field"
    INTENT_NOT_TARGETED_BY_PROJECT = "intent_not_targeted_by_project"
    INTENT_TARGET_COMPLETED = "intent_target_completed"
    REQUIRED_FILTER_UNAVAILABLE = "required_filter_unavailable"
    INSUFFICIENT_ACTIONABLE_PRODUCTIVE_WINDOW = (
        "insufficient_actionable_productive_window"
    )


class AcquisitionIntentEvidenceGap(str, Enum):
    SETUP_CAPABILITIES_MISSING = "setup_capabilities_missing"
    PRODUCTIVE_WINDOW_EVIDENCE_MISSING = (
        "productive_window_evidence_missing"
    )
    WEATHER_EVIDENCE_INSUFFICIENT = "weather_evidence_insufficient"
    FILTER_PROFILE_EVIDENCE_INSUFFICIENT = (
        "filter_profile_evidence_insufficient"
    )
    LUNAR_EVIDENCE_INSUFFICIENT = "lunar_evidence_insufficient"


@dataclass(frozen=True, slots=True)
class AcquisitionIntentEligibilityAssessment:
    acquisition_intent_id: str
    status: AcquisitionIntentEligibilityStatus
    blocking_reasons: tuple[AcquisitionIntentEligibilityReason, ...]
    evidence_gaps: tuple[AcquisitionIntentEvidenceGap, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.acquisition_intent_id, str)
            or not self.acquisition_intent_id.strip()
        ):
            raise ValueError("acquisition_intent_id_required")
        if not isinstance(self.status, AcquisitionIntentEligibilityStatus):
            raise TypeError("Expected AcquisitionIntentEligibilityStatus")
        if not isinstance(self.blocking_reasons, tuple):
            raise TypeError("blocking_reasons_must_be_tuple")
        if not all(
            isinstance(reason, AcquisitionIntentEligibilityReason)
            for reason in self.blocking_reasons
        ):
            raise TypeError(
                "blocking_reasons_must_contain_eligibility_reasons"
            )
        if len(set(self.blocking_reasons)) != len(self.blocking_reasons):
            raise ValueError("duplicate_blocking_reason")
        if not isinstance(self.evidence_gaps, tuple):
            raise TypeError("evidence_gaps_must_be_tuple")
        if not all(
            isinstance(gap, AcquisitionIntentEvidenceGap)
            for gap in self.evidence_gaps
        ):
            raise TypeError("evidence_gaps_must_contain_evidence_gaps")
        if len(set(self.evidence_gaps)) != len(self.evidence_gaps):
            raise ValueError("duplicate_evidence_gap")

        if self.status is AcquisitionIntentEligibilityStatus.ELIGIBLE:
            if self.blocking_reasons or self.evidence_gaps:
                raise ValueError("eligible_must_not_have_reasons_or_gaps")
            return
        if self.status is AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE:
            if not self.blocking_reasons or self.evidence_gaps:
                raise ValueError(
                    "not_eligible_requires_reasons_without_evidence_gaps"
                )
            return
        if self.blocking_reasons or not self.evidence_gaps:
            raise ValueError(
                "insufficient_evidence_requires_gaps_without_reasons"
            )
