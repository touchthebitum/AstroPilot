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
    state = project_state(object_name)

    if state is None:
        return 0

    importance = project.get("importance", 5)
    target = state["target_hours"]

    if target <= 0:
        return 0

    completion = state["progress"] / 100
    remaining = state["remaining"]

    if completion < 0.20:
        completion_bonus = 0
    elif completion < 0.50:
        completion_bonus = 3
    elif completion < 0.75:
        completion_bonus = 7
    elif completion < 0.90:
        completion_bonus = 12
    else:
        completion_bonus = 20

    remaining_pressure = min(remaining, 20)

    base_priority = completion_bonus + remaining_pressure

    return round(
        base_priority * (importance / 5),
        1,
    )


def project_roi(object_name):
    projects = get_projects()

    if object_name not in projects:
        return 0

    project = projects[object_name]
    state = project_state(object_name)

    if state is None:
        return 0

    remaining = state["remaining"]

    if remaining <= 0:
        return 0

    importance = project.get("importance", 5)
    progress = state["progress"]

    completion_multiplier = 1 + progress / 100

    roi = (
        importance
        * completion_multiplier
        / remaining
    )

    return round(roi, 2)


def closure_bonus(
    name,
    available_hours=3.0,
):
    remaining = project_remaining_hours(name)

    if remaining is None or remaining <= 0:
        return 0

    if remaining <= available_hours:
        return 15

    if remaining <= available_hours * 2:
        return 6

    if remaining <= available_hours * 3:
        return 3

    return 0


def simulated_portfolio_score(project):
    remaining = (
        project["target_hours"]
        - project["hours"]
    )

    progress = (
        project["hours"]
        / project["target_hours"]
        * 100
    )

    importance = project.get(
        "importance",
        5,
    )

    closure_bonus = 0

    if remaining > 0:
        closure_bonus = min(
            40,
            round(120 / remaining, 1),
        )

    return (
        importance * 10
        + progress * 0.5
        + closure_bonus
    )
