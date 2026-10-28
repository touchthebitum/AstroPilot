"""Public transport assessment for one evaluated acquisition intent."""

from dataclasses import dataclass
from decision.models.actionability_refusal import ActionabilityRefusal

from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityReason,
    AcquisitionIntentEligibilityStatus,
    AcquisitionIntentEvidenceGap,
)


@dataclass(frozen=True, slots=True)
class AcquisitionIntentAssessment:
    acquisition_intent_id: str
    filter_type: str
    label: str
    status: AcquisitionIntentEligibilityStatus
    reason_codes: tuple[str, ...]
    actionability_refusal: ActionabilityRefusal | None = None

    def __post_init__(self) -> None:
        for name in ("acquisition_intent_id", "filter_type", "label"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if not isinstance(self.status, AcquisitionIntentEligibilityStatus):
            raise TypeError("status_must_be_acquisition_intent_eligibility_status")
        if not isinstance(self.reason_codes, tuple):
            raise TypeError("reason_codes_must_be_tuple")
        if not all(isinstance(code, str) for code in self.reason_codes):
            raise TypeError("reason_codes_must_contain_strings")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("duplicate_reason_code")

        if self.actionability_refusal is not None:
            if not isinstance(self.actionability_refusal, ActionabilityRefusal):
                raise TypeError("Expected ActionabilityRefusal")
            expected_status = (
                "not_eligible" if self.actionability_refusal.status.value == "constraints_refusal"
                else "insufficient_evidence"
            )
            if self.status.value != expected_status or self.actionability_refusal.cause_code not in self.reason_codes:
                raise ValueError("intent_refusal_evidence_mismatch")

        if self.status is AcquisitionIntentEligibilityStatus.ELIGIBLE:
            if self.reason_codes:
                raise ValueError("eligible_must_not_have_reason_codes")
            return
        allowed = (
            {reason.value for reason in AcquisitionIntentEligibilityReason}
            if self.status is AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE
            else {gap.value for gap in AcquisitionIntentEvidenceGap}
        )
        if not self.reason_codes or any(
            code not in allowed for code in self.reason_codes
        ):
            raise ValueError("reason_codes_inconsistent_with_status")
