from decision.portfolio.candidate_scoring import (
    portfolio_candidate_bonus,
)

def test_portfolio_candidate_bonus_preserves_formula():
    score = portfolio_candidate_bonus(
        project_part=8,
        roi_bonus=1,
        closure_bonus=3,
        completion_bonus=14,
        opportunity_bonus=2,
        diversity_bonus=4,
    )

    assert score == 32
