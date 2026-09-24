from dataclasses import dataclass, field
from enum import Enum

from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelectionStatus,
)
from decision.models.acquisition_intent_assessment import (
    AcquisitionIntentAssessment,
)
from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityStatus,
)
from decision.models.acquisition_intent_remaining_progress import AcquisitionIntentRemainingProgress


class CandidateProvenance(str, Enum):
    PROJECT = "project"
    DISCOVERY = "discovery"


@dataclass
class Candidate:
    name: str
    catalog_key: str

    priority: float | None
    astro_score: float
    final_score: float
    decision_score: float

    portfolio_score: float | None

    global_score: float
    setup_score: float
    best_setup: str | None

    closure_bonus: float | None

    acquired_hours: float | None = 0.0
    acquisition_intent_remaining_progress: tuple[AcquisitionIntentRemainingProgress, ...] = ()
    provenance: CandidateProvenance = CandidateProvenance.PROJECT
    imaging_field_id: str | None = None
    selected_acquisition_intent_id: str | None = None
    viable_acquisition_intent_ids: tuple[str, ...] = ()
    acquisition_intent_selection_status: (
        AcquisitionIntentSelectionStatus | None
    ) = None
    acquisition_intent_assessments: tuple[
        AcquisitionIntentAssessment, ...
    ] = ()
    reasons: list[str] = field(default_factory=list)
    strategy_scores: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, CandidateProvenance):
            raise ValueError("provenance must be a CandidateProvenance")
        if (
            self.provenance is CandidateProvenance.DISCOVERY
            and self.imaging_field_id is not None
        ):
            raise ValueError("discovery candidates cannot have imaging_field_id")
        if self.imaging_field_id is not None and (
            not isinstance(self.imaging_field_id, str)
            or not self.imaging_field_id.strip()
        ):
            raise ValueError("imaging_field_id must be a non-empty string")
        if self.selected_acquisition_intent_id is not None and (
            not isinstance(self.selected_acquisition_intent_id, str)
            or not self.selected_acquisition_intent_id.strip()
        ):
            raise ValueError(
                "selected_acquisition_intent_id must be a non-empty string"
            )
        if not isinstance(self.viable_acquisition_intent_ids, tuple):
            raise TypeError("viable_acquisition_intent_ids must be a tuple")
        if not all(
            isinstance(intent_id, str) and intent_id.strip()
            for intent_id in self.viable_acquisition_intent_ids
        ):
            raise ValueError(
                "viable_acquisition_intent_ids must contain non-empty strings"
            )
        if len(set(self.viable_acquisition_intent_ids)) != len(
            self.viable_acquisition_intent_ids
        ):
            raise ValueError(
                "viable_acquisition_intent_ids must not contain duplicates"
            )
        if (
            self.acquisition_intent_selection_status is not None
            and not isinstance(
                self.acquisition_intent_selection_status,
                AcquisitionIntentSelectionStatus,
            )
        ):
            raise TypeError(
                "acquisition_intent_selection_status must be an "
                "AcquisitionIntentSelectionStatus or None"
            )
        if not isinstance(self.acquisition_intent_assessments, tuple) or not all(
            isinstance(item, AcquisitionIntentAssessment)
            for item in self.acquisition_intent_assessments
        ):
            raise TypeError(
                "acquisition_intent_assessments must contain intent assessments"
            )
        assessment_ids = tuple(
            item.acquisition_intent_id
            for item in self.acquisition_intent_assessments
        )
        if len(set(assessment_ids)) != len(assessment_ids):
            raise ValueError("duplicate_acquisition_intent_assessment")
        self._validate_acquisition_intent_selection_provenance()
        self._validate_acquisition_intent_assessment_consistency()

    def _validate_acquisition_intent_selection_provenance(self) -> None:
        selected = self.selected_acquisition_intent_id
        viable = self.viable_acquisition_intent_ids
        status = self.acquisition_intent_selection_status
        if status is None:
            if selected is not None or viable or self.acquisition_intent_assessments:
                raise ValueError(
                    "acquisition intent provenance requires a selection status"
                )
            return
        if status is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT:
            if selected is not None or viable:
                raise ValueError(
                    "no eligible intent requires no selected or viable intent"
                )
            return
        if status is AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE:
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

    def _validate_acquisition_intent_assessment_consistency(self) -> None:
        assessments = self.acquisition_intent_assessments
        if not assessments:
            return

        status = self.acquisition_intent_selection_status
        selected = self.selected_acquisition_intent_id
        viable = self.viable_acquisition_intent_ids
        eligible_ids = {
            item.acquisition_intent_id
            for item in assessments
            if item.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
        }

        if status is AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT:
            if eligible_ids:
                raise ValueError(
                    "no eligible intent cannot have eligible assessments"
                )
            return
        if status is AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT:
            if eligible_ids != {selected}:
                raise ValueError(
                    "single eligible intent requires exactly its selected "
                    "assessment to be eligible"
                )
            return
        if status is AcquisitionIntentSelectionStatus.PREFERRED:
            if selected not in eligible_ids:
                raise ValueError(
                    "preferred selection requires its selected assessment "
                    "to be eligible"
                )
            return
        if not set(viable).issubset(eligible_ids):
            raise ValueError(
                "no clear preference requires every viable assessment "
                "to be eligible"
            )

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)
