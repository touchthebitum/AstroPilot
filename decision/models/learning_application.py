"""Immutable fact that an explicit LearningSignal was accepted for future use."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LearningApplicationOutcome(str, Enum):
    APPLIED = "applied"
    ALREADY_APPLIED = "already_applied"


@dataclass(frozen=True, slots=True)
class LearningApplication:
    application_id: str
    signal_id: str
    applied_at: datetime

    def __post_init__(self) -> None:
        for name in ("application_id", "signal_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if not isinstance(self.applied_at, datetime):
            raise TypeError("applied_at_must_be_datetime")
        if self.applied_at.tzinfo is None or self.applied_at.utcoffset() is None:
            raise ValueError("applied_at_timezone_required")


@dataclass(frozen=True, slots=True)
class LearningApplicationResult:
    application: LearningApplication
    outcome: LearningApplicationOutcome

    def __post_init__(self) -> None:
        if type(self.application) is not LearningApplication:
            raise TypeError("application_must_be_learning_application")
        if not isinstance(self.outcome, LearningApplicationOutcome):
            raise TypeError("Expected LearningApplicationOutcome")
