from __future__ import annotations

from astropilot.user_profile import get_projects

from decision.portfolio.project_state import (
    project_remaining_hours,
    project_state,
)


def project_priority(object_name):
    projects = get_projects()

    if object_name not in projects:
        return 0

    project = projects[object_name]

    importance = float(
        project.get("importance", 5)
    )

    return round(
        min(100.0, max(0.0, importance * 10)),
        1,
    )


def closure_bonus_for_remaining(
    remaining,
    available_hours=3.0,
):
    if remaining is None or remaining <= 0:
        return 0

    if available_hours <= 0:
        return 0

    if remaining <= available_hours:
        return 15

    if remaining <= available_hours * 2:
        return 6

    if remaining <= available_hours * 3:
        return 3

    return 0


def closure_bonus(
    name,
    available_hours=3.0,
):
    remaining = project_remaining_hours(name)

    return closure_bonus_for_remaining(
        remaining,
        available_hours,
    )


def simulated_portfolio_score(
    project,
    available_hours=3.0,
):
    remaining = (
        project["target_hours"]
        - project["hours"]
    )

    importance = project.get(
        "importance",
        5,
    )

    closure = closure_bonus_for_remaining(
        remaining,
        available_hours,
    )

    return (
        importance * 6
        + closure
    )
