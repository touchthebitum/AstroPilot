"""Pareto comparison result for two lunar-contamination estimates."""

from dataclasses import dataclass
from enum import Enum


class LunarContaminationComparisonStatus(str, Enum):
    DOMINATES = "dominates"
    DOMINATED = "dominated"
    EQUIVALENT = "equivalent"
    INCOMPARABLE = "incomparable"


@dataclass(frozen=True, slots=True)
class LunarContaminationComparison:
    """Direction of the comparison from the left profile to the right one."""

    left_filter_profile_id: str
    right_filter_profile_id: str
    status: LunarContaminationComparisonStatus

    def __post_init__(self) -> None:
        self._validate_profile_id(
            self.left_filter_profile_id,
            "left_filter_profile_id",
        )
        self._validate_profile_id(
            self.right_filter_profile_id,
            "right_filter_profile_id",
        )
        if not isinstance(self.status, LunarContaminationComparisonStatus):
            raise TypeError(
                "status must be LunarContaminationComparisonStatus"
            )

    @staticmethod
    def _validate_profile_id(value: object, name: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must not be empty")
