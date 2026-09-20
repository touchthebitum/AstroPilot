from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class UserSelectionSource(str, Enum):
    PRIMARY_RECOMMENDATION = "primary_recommendation"
    ALTERNATIVE = "alternative"
    OTHER_EVALUATED_TARGET = "other_evaluated_target"
    DECLINED = "declined"


@dataclass(frozen=True, slots=True)
class UserSelection:
    selection_id: str
    decision_id: str
    selected_catalog_key: str | None
    source: UserSelectionSource
    selected_at: datetime
    selected_imaging_field_id: str | None = None
    selected_acquisition_intent_id: str | None = None

    def __post_init__(self):
        for name in ("selection_id", "decision_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")

        if not isinstance(self.source, UserSelectionSource):
            raise TypeError("Expected UserSelectionSource")
        if not isinstance(self.selected_at, datetime):
            raise TypeError("selected_at_must_be_datetime")
        if self.selected_at.tzinfo is None or self.selected_at.utcoffset() is None:
            raise ValueError("selected_at_timezone_required")

        if self.source is UserSelectionSource.DECLINED:
            if (
                self.selected_catalog_key is not None
                or self.selected_imaging_field_id is not None
                or self.selected_acquisition_intent_id is not None
            ):
                raise ValueError("declined_selection_requires_no_target")
            return

        if (
            not isinstance(self.selected_catalog_key, str)
            or not self.selected_catalog_key.strip()
        ):
            raise ValueError("selected_catalog_key_required")
        if self.selected_imaging_field_id is not None and (
            not isinstance(self.selected_imaging_field_id, str)
            or not self.selected_imaging_field_id.strip()
        ):
            raise ValueError("selected_imaging_field_id_must_be_non_empty_string")
        if self.selected_acquisition_intent_id is not None and (
            not isinstance(self.selected_acquisition_intent_id, str)
            or not self.selected_acquisition_intent_id.strip()
        ):
            raise ValueError(
                "selected_acquisition_intent_id_must_be_non_empty_string"
            )
