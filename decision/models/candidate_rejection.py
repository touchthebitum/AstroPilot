from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import overload

from decision.models.candidate import Candidate, CandidateProvenance


class CandidateRejectionBasis(str, Enum):
    NON_POSITIVE_EVALUATION_SCORE = "non_positive_evaluation_score"


@dataclass(frozen=True)
class CandidateRejection:
    target: str
    catalog_key: str
    provenance: CandidateProvenance
    basis: CandidateRejectionBasis
    evaluation_score: float


@dataclass(frozen=True)
class CandidateBuildResult(Sequence[Candidate]):
    candidates: tuple[Candidate, ...]
    rejections: tuple[CandidateRejection, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "rejections", tuple(self.rejections))

    def __len__(self) -> int:
        return len(self.candidates)

    @overload
    def __getitem__(self, index: int) -> Candidate: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Candidate, ...]: ...

    def __getitem__(self, index):
        return self.candidates[index]

    def __iter__(self) -> Iterator[Candidate]:
        return iter(self.candidates)
