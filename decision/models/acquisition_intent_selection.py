"""Immutable result of selecting among eligible acquisition intents."""

from dataclasses import dataclass
from enum import Enum


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
