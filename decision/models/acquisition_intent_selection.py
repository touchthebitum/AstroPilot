"""Immutable result of selecting among eligible acquisition intents."""

from dataclasses import dataclass
from enum import Enum

from decision.models.acquisition_intent_assessment import (
    AcquisitionIntentAssessment,
)
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityAssessment,
)


class AcquisitionIntentSelectionStatus(str, Enum):
    NO_ELIGIBLE_INTENT = "no_eligible_intent"
    SINGLE_ELIGIBLE_INTENT = "single_eligible_intent"
    PREFERRED = "preferred"
    NO_CLEAR_PREFERENCE = "no_clear_preference"


NO_ELIGIBLE_INTENT = "NO_ELIGIBLE_INTENT"
ONLY_ELIGIBLE_INTENT = "ONLY_ELIGIBLE_INTENT"
UNIQUE_NON_DOMINATED_INTENT = "UNIQUE_NON_DOMINATED_INTENT"
MULTIPLE_NON_DOMINATED_INTENTS = "MULTIPLE_NON_DOMINATED_INTENTS"

ACQUISITION_INTENT_SELECTION_REASON_CODES = (
    NO_ELIGIBLE_INTENT,
    ONLY_ELIGIBLE_INTENT,
    UNIQUE_NON_DOMINATED_INTENT,
    MULTIPLE_NON_DOMINATED_INTENTS,
)

_EXPECTED_REASON_CODE = {
    AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT: NO_ELIGIBLE_INTENT,
    AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT: (
        ONLY_ELIGIBLE_INTENT
    ),
    AcquisitionIntentSelectionStatus.PREFERRED: UNIQUE_NON_DOMINATED_INTENT,
    AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE: (
        MULTIPLE_NON_DOMINATED_INTENTS
    ),
}


@dataclass(frozen=True, slots=True)
class AcquisitionIntentSelection:
    selected_acquisition_intent_id: str | None
    viable_acquisition_intent_ids: tuple[str, ...]
    status: AcquisitionIntentSelectionStatus
    reason_codes: tuple[str, ...]
    eligibility_assessments: tuple[
        AcquisitionIntentEligibilityAssessment, ...
    ] = ()
    acquisition_intent_assessments: tuple[
        AcquisitionIntentAssessment, ...
    ] = ()

    def __post_init__(self) -> None:
        selected = self.selected_acquisition_intent_id
        if selected is not None:
            self._validate_intent_id(selected, "selected_acquisition_intent_id")
        if not isinstance(self.viable_acquisition_intent_ids, tuple):
            raise TypeError("viable_acquisition_intent_ids must be a tuple")
        for intent_id in self.viable_acquisition_intent_ids:
            self._validate_intent_id(
                intent_id,
                "viable acquisition intent ID",
            )
        if len(set(self.viable_acquisition_intent_ids)) != len(
            self.viable_acquisition_intent_ids
        ):
            raise ValueError(
                "viable_acquisition_intent_ids must not contain duplicates"
            )
        if not isinstance(self.status, AcquisitionIntentSelectionStatus):
            raise TypeError("status must be AcquisitionIntentSelectionStatus")
        if not isinstance(self.reason_codes, tuple):
            raise TypeError("reason_codes must be a tuple")
        if not all(isinstance(code, str) for code in self.reason_codes):
            raise TypeError("reason_codes must contain strings")
        if self.reason_codes != (_EXPECTED_REASON_CODE[self.status],):
            raise ValueError("reason_codes are inconsistent with selection status")
        if not isinstance(self.eligibility_assessments, tuple) or not all(
            isinstance(item, AcquisitionIntentEligibilityAssessment)
            for item in self.eligibility_assessments
        ):
            raise TypeError(
                "eligibility_assessments must contain eligibility assessments"
            )
        if not isinstance(self.acquisition_intent_assessments, tuple) or not all(
            isinstance(item, AcquisitionIntentAssessment)
            for item in self.acquisition_intent_assessments
        ):
            raise TypeError(
                "acquisition_intent_assessments must contain intent assessments"
            )
        eligibility_ids = tuple(
            item.acquisition_intent_id for item in self.eligibility_assessments
        )
        assessment_ids = tuple(
            item.acquisition_intent_id
            for item in self.acquisition_intent_assessments
        )
        if assessment_ids and eligibility_ids != assessment_ids:
            raise ValueError("assessment_transport_must_match_eligibility_order")

        viable = self.viable_acquisition_intent_ids
        if self.status is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT:
            if selected is not None or viable:
                raise ValueError(
                    "no eligible intent requires no selected or viable intent"
                )
            return
        if self.status is AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE:
            if selected is not None or len(viable) < 2:
                raise ValueError(
                    "no clear preference requires multiple viable intents and "
                    "no selection"
                )
            return
        if selected is None or viable != (selected,):
            raise ValueError(
                "single or preferred selection requires its sole viable intent"
            )

    @staticmethod
    def _validate_intent_id(value: object, name: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must not be empty")
