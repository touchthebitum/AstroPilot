from dataclasses import dataclass
from enum import Enum


class RecommendationReasonCategory(str, Enum):
    RELIABILITY = "reliability"


class RecommendationReasonScope(str, Enum):
    TARGET = "target"
    NIGHT = "night"


@dataclass(frozen=True, slots=True, kw_only=True)
class RecommendationReason:
    category: RecommendationReasonCategory | None = None
    scope: RecommendationReasonScope
    direction: str | None = None
    importance: str | None = None
    basis: str | None = None
    message: str | None = None
    evidence_ref: object | None = None

    def __post_init__(self):
        if not isinstance(self.scope, RecommendationReasonScope):
            raise TypeError("Expected RecommendationReasonScope")
        if self.category is not None and not isinstance(
            self.category, RecommendationReasonCategory
        ):
            raise TypeError("Expected RecommendationReasonCategory")
