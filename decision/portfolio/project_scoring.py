from __future__ import annotations

from decision.portfolio.session_capacity import explicit_session_hours

from decision.portfolio.project_state import (
    project_state_from_project,
)


def project_priority(object_name, projects):
    if object_name not in projects:
        return 0

    project = projects[object_name]

    importance = float(
        # No user preference means no priority contribution, never midpoint
        # importance that can outrank an explicitly low-priority project.
        project.get("importance", 0)
    )

    return round(
        min(100.0, max(0.0, importance * 10)),
        1,
    )


def closure_bonus_for_remaining(
    remaining,
    available_hours=None,
):
    if remaining is None or remaining <= 0:
        return 0

    available_hours = explicit_session_hours(available_hours)
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
    available_hours=None,
    *,
    projects,
):
    state = project_state_from_project(projects.get(name))
    remaining = state["remaining"] if state is not None else None

    return closure_bonus_for_remaining(
        remaining,
        available_hours,
    )


def simulated_portfolio_score(
    project,
    available_hours=None,
):
    remaining = (
        project["target_hours"]
        - project["hours"]
    )

    importance = project.get("importance", 0)

    closure = closure_bonus_for_remaining(
        remaining,
        available_hours,
    )

    return (
        importance * 6
        + closure
    )
