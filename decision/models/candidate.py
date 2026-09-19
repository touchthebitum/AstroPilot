from dataclasses import dataclass, field
from enum import Enum


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
    provenance: CandidateProvenance = CandidateProvenance.PROJECT
    imaging_field_id: str | None = None
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

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)
