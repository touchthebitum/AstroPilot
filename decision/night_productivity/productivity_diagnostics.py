from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


PRODUCTIVE_SLICE_THRESHOLD = 0.70


@dataclass(frozen=True, slots=True)
class ProductivityLosses:
    cloud: float
    moon: float
    altitude: float
    humidity: float
    wind: float


@dataclass(frozen=True, slots=True)
class SliceProductivityEvaluation:
    score: float
    losses: ProductivityLosses


@dataclass(frozen=True, slots=True)
class ProductivityBreakdown:
    evaluated_slice_count: int
    productive_slice_count: int
    best_slice_start: datetime
    best_slice_end: datetime
    best_slice_score: float
    best_slice_tie_count: int
    productive_slice_threshold: float
    losses: ProductivityLosses
