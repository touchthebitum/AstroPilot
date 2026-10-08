from __future__ import annotations

from typing import TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime
from decision.models.lunar_evidence_snapshot import (
    LunarEvidenceSnapshot, validate_lunar_snapshot,
)

from decision.filtering.selected_filter import SelectedFilter
from decision.models.session_availability import SessionAvailability
from decision.weather.weather_forecast import WeatherForecast
from decision.models.acquisition_intent_remaining_progress import (
    AcquisitionIntentRemainingProgress,
)


if TYPE_CHECKING:
    from decision.mission.modern_mission_authorization import ModernMissionAuthorization


@dataclass(frozen=True)
class MissionInput:
    window_start: datetime | None
    window_end: datetime | None
    astronomical_hours: float | None
    weather: WeatherForecast | None
    moon_penalty: float | None
    recommended_hours: float
    expected_gain: float
    selected_filter: SelectedFilter | None = None
    availability: SessionAvailability | None = None
    mission_id: str | None = None
    decision_id: str | None = None
    selection_id: str | None = None
    imaging_field_id: str | None = None
    acquisition_intent_id: str | None = None
    acquisition_capacity: AcquisitionIntentRemainingProgress | None = None
    evidence_only: bool = False

    lunar_evidence_snapshot: LunarEvidenceSnapshot | None = None
    creation_authorization: ModernMissionAuthorization | None = None

    def __post_init__(self):
        if self.lunar_evidence_snapshot is not None and (
            self.imaging_field_id is None or self.acquisition_intent_id is None
        ):
            raise ValueError("lunar_snapshot_mission_identity_required")
        validate_lunar_snapshot(self.lunar_evidence_snapshot,
            imaging_field_id=self.imaging_field_id,
            acquisition_intent_id=self.acquisition_intent_id)
        capacity = self.acquisition_capacity
        if capacity is not None:
            if not isinstance(capacity, AcquisitionIntentRemainingProgress):
                raise TypeError("Expected AcquisitionIntentRemainingProgress")
            if capacity.acquisition_intent_id != self.acquisition_intent_id:
                raise ValueError("acquisition_capacity_intent_mismatch")
            ceiling = capacity.remaining_hours
            if ceiling is None:
                if self.recommended_hours != 0 or self.expected_gain != 0:
                    raise ValueError("unknown_acquisition_capacity_must_fail_closed")
            elif self.recommended_hours > ceiling:
                raise ValueError("recommended_hours_exceeds_acquisition_capacity")
        provenance = (self.mission_id, self.decision_id, self.selection_id)
        if any(value is not None for value in provenance) and any(
            not isinstance(value, str) or not value.strip()
            for value in provenance
        ):
            raise ValueError("mission_provenance_required")
        if self.imaging_field_id is not None and (
            not isinstance(self.imaging_field_id, str)
            or not self.imaging_field_id.strip()
        ):
            raise ValueError("imaging_field_id_must_be_non_empty_string")
        if self.acquisition_intent_id is not None and (
            not isinstance(self.acquisition_intent_id, str)
            or not self.acquisition_intent_id.strip()
        ):
            raise ValueError(
                "acquisition_intent_id_must_be_non_empty_string"
            )
