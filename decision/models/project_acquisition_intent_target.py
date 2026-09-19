import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectAcquisitionIntentTarget:
    acquisition_intent_id: str
    target_hours: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.acquisition_intent_id, str)
            or not self.acquisition_intent_id.strip()
        ):
            raise ValueError(
                "acquisition_intent_id must be a non-empty string"
            )
        if (
            not isinstance(self.target_hours, (int, float))
            or isinstance(self.target_hours, bool)
            or not math.isfinite(self.target_hours)
            or self.target_hours <= 0
        ):
            raise ValueError("target_hours must be finite and positive")
        object.__setattr__(self, "target_hours", float(self.target_hours))
