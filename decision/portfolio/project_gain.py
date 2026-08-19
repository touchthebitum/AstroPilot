from __future__ import annotations

from astropilot.user_profile import get_projects

from decision.portfolio.project_state import (
    project_remaining_hours,
    project_state,
)


def marginal_gain_factor(progress):
    if progress >= 95:
        return 0.5

    if progress >= 80:
        return 0.8

    if progress >= 50:
        return 1.0

    if progress >= 20:
        return 1.2

    return 1.4


def portfolio_gain_if_shot(
    object_name,
    session_hours=3.0,
):
    state = project_state(object_name)

    if state is None:
        return 0

    before = state["progress"]
    marginal_factor = marginal_gain_factor(
        before
    )

    target_hours = state["target_hours"]

    if target_hours <= 0:
        return 0

    simulated_hours = min(
        state["hours"] + session_hours,
        target_hours,
    )

    after = round(
        simulated_hours / target_hours * 100,
        1,
    )

    gain = after - before
    gain *= marginal_factor

    return round(gain, 1)


def session_portfolio_gain(
    name,
    session_hours=3.0,
):
    remaining = project_remaining_hours(name)

    if remaining is None or remaining <= 0:
        return 0

    gain_hours = min(
        session_hours,
        remaining,
    )

    project = get_projects().get(
        name,
        {},
    )
    project_total = project.get(
        "target_hours",
        0,
    )

    if project_total <= 0:
        return 0

    gain_percent = (
        gain_hours
        / project_total
        * 100
    )

    return gain_percent

def session_roi(
    name,
    session_hours=3.0,
):
    if session_hours <= 0:
        return 0

    gain = session_portfolio_gain(
        name,
        session_hours=session_hours,
    )

    return round(
        gain / session_hours,
        2,
    )
