from __future__ import annotations


def portfolio_candidate_bonus(
    *,
    project_part: float,
    roi_bonus: float,
    closure_bonus: float,
    marginal_progress_bonus: float,
    opportunity_bonus: float,
    diversity_bonus: float,
) -> float:
    return (
        project_part
        + roi_bonus
        + closure_bonus
        + marginal_progress_bonus
        + opportunity_bonus
        + diversity_bonus
    )