from __future__ import annotations


class NightStrategyEngine:
    """
    Calcule les scores associés aux différents modes
    de stratégie nocturne.
    """

    STRATEGY_MODES = (
        "balanced",
        "roi",
        "completion",
        "diversification",
        "risk",
    )

    def __init__(self, strategy_weights_provider):
        self.strategy_weights_provider = strategy_weights_provider

    def compute_strategy_scores(
        self,
        *,
        astro_part: float,
        roi_bonus: float,
        postponement_net_impact: float,
        marginal_progress_bonus: float,
        closure_bonus: float,
        diversity_bonus: float,
        decision_mode: str,
        fallback_score: float,
    ) -> tuple[dict[str, float], float]:
        strategy_scores: dict[str, float] = {}

        for mode in self.STRATEGY_MODES:
            weights = self.strategy_weights_provider(mode)

            strategy_scores[mode] = round(
                astro_part * weights["astro"]
                + roi_bonus * weights["roi"]
                + postponement_net_impact * weights["report"]
                + marginal_progress_bonus * weights["progress"]
                + closure_bonus * weights["closure"]
                + diversity_bonus * weights["diversity"],
                1,
            )

        if decision_mode == "balanced":
            strategy_scores["balanced"] = fallback_score
            decision_score = fallback_score
        else:
            decision_score = strategy_scores.get(
                decision_mode,
                fallback_score,
            )

        return strategy_scores, decision_score
