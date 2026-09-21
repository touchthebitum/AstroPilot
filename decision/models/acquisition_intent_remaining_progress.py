"""Read-only, derived progress for one acquisition intent."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AcquisitionIntentRemainingProgress:
    acquisition_intent_id: str
    acquired_seconds: float | None
    acquired_hours: float | None
    target_hours: float | None
    remaining_hours: float | None

    @property
    def completed(self) -> bool:
        return (self.target_hours is not None
                and self.acquired_hours is not None
                and self.remaining_hours == 0)
