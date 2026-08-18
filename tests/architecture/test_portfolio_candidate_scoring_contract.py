from decision.portfolio.candidate_scoring import (
    portfolio_candidate_bonus,
    portfolio_rank_bonus,
)


def test_portfolio_rank_bonus_rewards_top_three():
    ranking = [
        "M31",
        "IC1396",
        "Sh2-129",
        "Rosette",
    ]

    assert portfolio_rank_bonus(
        catalog_key="M31",
        portfolio_ranking=ranking,
    ) == 12

    assert portfolio_rank_bonus(
        catalog_key="IC1396",
        portfolio_ranking=ranking,
    ) == 6

    assert portfolio_rank_bonus(
        catalog_key="Sh2-129",
        portfolio_ranking=ranking,
    ) == 3

    assert portfolio_rank_bonus(
        catalog_key="Rosette",
        portfolio_ranking=ranking,
    ) == 0


def test_portfolio_candidate_bonus_preserves_formula():
    score = portfolio_candidate_bonus(
        project_part=8,
        roi_bonus=1,
        closure_bonus=3,
        completion_bonus=14,
        opportunity_bonus=2,
        regret_bonus=1,
        progression_bonus=12,
        diversity_bonus=4,
        rank_bonus=6,
    )

    assert score == 51