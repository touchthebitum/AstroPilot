"""Explicit preference result for two eligible acquisition intents."""

from dataclasses import dataclass
from enum import Enum


class AcquisitionIntentPreferenceStatus(str, Enum):
    LEFT_PREFERRED = "left_preferred"
    RIGHT_PREFERRED = "right_preferred"
    NO_CLEAR_PREFERENCE = "no_clear_preference"


LOWER_LUNAR_CONTAMINATION = "LOWER_LUNAR_CONTAMINATION"
LUNAR_CONTAMINATION_EQUIVALENT = "LUNAR_CONTAMINATION_EQUIVALENT"
LUNAR_CONTAMINATION_INCOMPARABLE = "LUNAR_CONTAMINATION_INCOMPARABLE"

ACQUISITION_INTENT_PREFERENCE_REASON_CODES = (
    LOWER_LUNAR_CONTAMINATION,
    LUNAR_CONTAMINATION_EQUIVALENT,
    LUNAR_CONTAMINATION_INCOMPARABLE,
)

_EXPECTED_REASON_CODES = {
    AcquisitionIntentPreferenceStatus.LEFT_PREFERRED: (
        LOWER_LUNAR_CONTAMINATION,
    ),
    AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED: (
        LOWER_LUNAR_CONTAMINATION,
    ),
    AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE: (
        LUNAR_CONTAMINATION_EQUIVALENT,
        LUNAR_CONTAMINATION_INCOMPARABLE,
    ),
}


@dataclass(frozen=True, slots=True)
class AcquisitionIntentPreference:
    """Preference determined solely from an existing lunar comparison."""

    left_acquisition_intent_id: str
    right_acquisition_intent_id: str
    status: AcquisitionIntentPreferenceStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        self._validate_intent_id(
            self.left_acquisition_intent_id,
            "left_acquisition_intent_id",
        )
        self._validate_intent_id(
            self.right_acquisition_intent_id,
            "right_acquisition_intent_id",
        )
        if not isinstance(self.status, AcquisitionIntentPreferenceStatus):
            raise TypeError(
                "status must be AcquisitionIntentPreferenceStatus"
            )
        if not isinstance(self.reason_codes, tuple):
            raise TypeError("reason_codes must be a tuple")
        if not all(isinstance(code, str) for code in self.reason_codes):
            raise TypeError("reason_codes must contain strings")
        if len(self.reason_codes) != 1:
            raise ValueError("exactly one reason code is required")
        if self.reason_codes[0] not in ACQUISITION_INTENT_PREFERENCE_REASON_CODES:
            raise ValueError("unsupported acquisition-intent preference reason")
        if self.reason_codes[0] not in _EXPECTED_REASON_CODES[self.status]:
            raise ValueError("reason code is inconsistent with preference status")

    @staticmethod
    def _validate_intent_id(value: object, name: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must not be empty")
