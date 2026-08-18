from __future__ import annotations


def portfolio_candidate_bonus(
    *,
    project_part: float,
    roi_bonus: float,
    closure_bonus: float,
    completion_bonus: float,
    opportunity_bonus: float,
    regret_bonus: float,
    diversity_bonus: float,
) -> float:
    return (
        project_part
        + roi_bonus
        + closure_bonus
        + completion_bonus
        + opportunity_bonus
        + regret_bonus
        + diversity_bonus
    )