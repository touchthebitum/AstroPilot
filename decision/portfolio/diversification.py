from __future__ import annotations

from astropilot.catalog import CATALOG
from decision.portfolio.project_state import (
    project_state_from_project,
)


def portfolio_category_load(projects):
    loads = {}

    for name, project in projects.items():
        state = project_state_from_project(project)
        remaining = state["remaining"]

        if remaining is None or remaining <= 0:
            continue

        obj = CATALOG.get(name, {})
        category = obj.get("type", "").lower()

        if not category:
            continue

        loads[category] = (
            loads.get(category, 0)
            + remaining
        )

    return loads


def diversification_bonus(name, projects):
    obj = CATALOG.get(name, {})
    category = obj.get("type", "").lower()

    if not category:
        return 0

    loads = portfolio_category_load(projects)

    if not loads:
        return 0

    total_load = sum(loads.values())

    if total_load <= 0:
        return 0

    category_load = loads.get(category, 0)
    category_share = category_load / total_load

    if category_share < 0.20:
        return 8

    if category_share < 0.35:
        return 4

    return 0
