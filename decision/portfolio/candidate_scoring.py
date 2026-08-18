from __future__ import annotations


def portfolio_rank_bonus(
    *,
    catalog_key: str,
    portfolio_ranking: list[str],
) -> float:
    if catalog_key not in portfolio_ranking:
        return 0

    rank = portfolio_ranking.index(catalog_key) + 1

    if rank == 1:
        return 12

    if rank == 2:
        return 6

    if rank == 3:
        return 3

    return 0


def portfolio_candidate_bonus(
    *,
    project_part: float,
    roi_bonus: float,
    closure_bonus: float,
    completion_bonus: float,
    opportunity_bonus: float,
    regret_bonus: float,
    progression_bonus: float,
    diversity_bonus: float,
    rank_bonus: float,
) -> float:
    return (
        project_part
        + roi_bonus
        + closure_bonus
        + completion_bonus
        + opportunity_bonus
        + regret_bonus
        + progression_bonus
        + diversity_bonus
        + rank_bonus
    )