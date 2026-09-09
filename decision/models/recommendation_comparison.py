from dataclasses import dataclass

from decision.models.recommendation_reason import RecommendationReason


@dataclass(frozen=True, slots=True)
class RecommendationComparison:
    primary_catalog_key: str
    alternative_catalog_key: str
    primary_only_reasons: tuple[RecommendationReason, ...] = ()
    alternative_only_reasons: tuple[RecommendationReason, ...] = ()
    shared_reasons: tuple[RecommendationReason, ...] = ()

    def __post_init__(self):
        for name in (
            "primary_only_reasons",
            "alternative_only_reasons",
            "shared_reasons",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
