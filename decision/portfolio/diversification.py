from __future__ import annotations

from astropilot.catalog import CATALOG
from astropilot.user_profile import get_projects

from decision.portfolio.project_state import (
    project_remaining_hours,
)


def portfolio_category_load():
    loads = {}

    for name, project in get_projects().items():
        remaining = project_remaining_hours(name)

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


def diversification_bonus(name):
    obj = CATALOG.get(name, {})
    category = obj.get("type", "").lower()

    if not category:
        return 0

    loads = portfolio_category_load()

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