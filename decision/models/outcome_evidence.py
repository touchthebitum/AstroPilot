"""Immutable observed facts linked to an Execution by identifier only.

Evidence does not confirm execution, assess outcomes, award portfolio credit,
or trigger learning. Missing records and missing durations remain unknown.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class OutcomeEvidenceCategory(str, Enum):
    FIELD = "field"
    TECHNICAL = "technical"
    ACQUISITION = "acquisition"
    IMAGE = "image"


class OutcomeEvidenceSource(str, Enum):
    """User-supplied facts; automated and imported provenance are not modeled yet."""

    USER = "user"


@dataclass(frozen=True, slots=True)
class OutcomeEvidence:
    """Shared provenance contract; instantiate a supported category-specific type."""

    evidence_id: str
    execution_id: str
    category: OutcomeEvidenceCategory
    observed_at: datetime
    source: OutcomeEvidenceSource

    def __post_init__(self):
        supported_categories = {
            FieldOutcomeEvidence: OutcomeEvidenceCategory.FIELD,
            TechnicalOutcomeEvidence: OutcomeEvidenceCategory.TECHNICAL,
            AcquisitionOutcomeEvidence: OutcomeEvidenceCategory.ACQUISITION,
            ImageOutcomeEvidence: OutcomeEvidenceCategory.IMAGE,
        }
        expected_category = supported_categories.get(type(self))
        if expected_category is None:
            raise TypeError("unsupported_outcome_evidence_type")
        for name in ("evidence_id", "execution_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if not isinstance(self.category, OutcomeEvidenceCategory):
            raise TypeError("Expected OutcomeEvidenceCategory")
        if self.category is not expected_category:
            raise ValueError("outcome_evidence_category_mismatch")
        if not isinstance(self.source, OutcomeEvidenceSource):
            raise TypeError("Expected OutcomeEvidenceSource")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at_must_be_datetime")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at_timezone_required")


@dataclass(frozen=True, slots=True)
class FieldOutcomeEvidence(OutcomeEvidence):
    """Field evidence provenance; no additional factual payload specified yet."""


@dataclass(frozen=True, slots=True)
class TechnicalOutcomeEvidence(OutcomeEvidence):
    """Technical evidence provenance; no additional factual payload specified yet."""


@dataclass(frozen=True, slots=True)
class AcquisitionOutcomeEvidence(OutcomeEvidence):
    """Independently supplied durations, with None meaning no observation.

    Actual capture duration measures capture time. Usable integration duration
    records explicitly supplied usable integration time. Neither supplies the
    other, and neither is derived from Execution timing.
    """

    actual_capture_duration: timedelta | None = None
    usable_integration_duration: timedelta | None = None

    def __post_init__(self):
        OutcomeEvidence.__post_init__(self)
        for name in ("actual_capture_duration", "usable_integration_duration"):
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, timedelta):
                raise TypeError(f"{name}_must_be_timedelta")
            if value < timedelta(0):
                raise ValueError(f"{name}_must_be_non_negative")


@dataclass(frozen=True, slots=True)
class ImageOutcomeEvidence(OutcomeEvidence):
    """Image evidence provenance; no additional factual payload specified yet."""
