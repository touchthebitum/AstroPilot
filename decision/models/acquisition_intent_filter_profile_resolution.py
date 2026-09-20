"""Typed result of resolving filter profiles for one acquisition intent."""

from dataclasses import dataclass
from enum import Enum


class AcquisitionIntentFilterProfileResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class AcquisitionIntentFilterProfileResolution:
    acquisition_intent_id: str
    status: AcquisitionIntentFilterProfileResolutionStatus
    matching_filter_profile_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.acquisition_intent_id, str):
            raise TypeError("acquisition_intent_id must be a string")
        if not self.acquisition_intent_id.strip():
            raise ValueError("acquisition_intent_id must not be empty")
        if not isinstance(
            self.status,
            AcquisitionIntentFilterProfileResolutionStatus,
        ):
            raise TypeError(
                "status must be AcquisitionIntentFilterProfileResolutionStatus"
            )
        if not isinstance(self.matching_filter_profile_ids, tuple):
            raise TypeError("matching_filter_profile_ids must be a tuple")

        seen_profile_ids: set[str] = set()
        for filter_profile_id in self.matching_filter_profile_ids:
            if not isinstance(filter_profile_id, str):
                raise TypeError("matching filter profile ID must be a string")
            if not filter_profile_id.strip():
                raise ValueError("matching filter profile ID must not be empty")
            if filter_profile_id in seen_profile_ids:
                raise ValueError(
                    "matching_filter_profile_ids must not contain duplicates"
                )
            seen_profile_ids.add(filter_profile_id)

        match_count = len(self.matching_filter_profile_ids)
        if (
            self.status
            is AcquisitionIntentFilterProfileResolutionStatus.RESOLVED
            and match_count != 1
        ):
            raise ValueError("resolved status requires exactly one matching profile")
        if (
            self.status
            is AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE
            and match_count != 0
        ):
            raise ValueError("unavailable status requires no matching profiles")
        if (
            self.status
            is AcquisitionIntentFilterProfileResolutionStatus.AMBIGUOUS
            and match_count < 2
        ):
            raise ValueError(
                "ambiguous status requires at least two matching profiles"
            )
