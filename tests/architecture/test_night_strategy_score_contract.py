from decision.engines.night_strategy_engine import NightStrategyEngine


def strategy_weights(mode):
    weights = {
        "balanced": {
            "astro": 1.0,
            "roi": 1.0,
            "report": 1.0,
            "completion": 1.0,
            "diversity": 1.0,
        },
        "roi": {
            "astro": 0.8,
            "roi": 2.0,
            "report": 0.8,
            "completion": 0.7,
            "diversity": 0.5,
        },
        "completion": {
            "astro": 0.8,
            "roi": 0.7,
            "report": 1.0,
            "completion": 2.0,
            "diversity": 0.5,
        },
        "diversification": {
            "astro": 0.8,
            "roi": 0.7,
            "report": 0.8,
            "completion": 0.5,
            "diversity": 2.0,
        },
        "risk": {
            "astro": 0.9,
            "roi": 0.6,
            "report": 2.0,
            "completion": 1.0,
            "diversity": 0.8,
        },
    }

    return weights[mode]


def test_balanced_mode_uses_final_score_as_decision_score():
    engine = NightStrategyEngine(strategy_weights)

    strategy_scores, decision_score = (
        engine.compute_strategy_scores(
            astro_part=70,
            roi_bonus=10,
            postponement_net_impact=5,
            completion_bonus=8,
            diversity_bonus=4,
            decision_mode="balanced",
            fallback_score=130.2,
        )
    )

    assert decision_score == 130.2
    assert strategy_scores["balanced"] == 130.2


def test_explicit_strategy_can_override_final_score():
    engine = NightStrategyEngine(strategy_weights)

    strategy_scores, decision_score = (
        engine.compute_strategy_scores(
            astro_part=70,
            roi_bonus=10,
            postponement_net_impact=5,
            completion_bonus=8,
            diversity_bonus=4,
            decision_mode="roi",
            fallback_score=130.2,
        )
    )

    assert decision_score == strategy_scores["roi"]
    assert decision_score != 130.2