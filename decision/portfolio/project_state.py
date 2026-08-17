from __future__ import annotations

from astropilot.user_profile import get_projects


def project_state(object_name):
    projects = get_projects()

    if object_name not in projects:
        return None

    project = projects[object_name]

    hours = float(
        project.get("hours", 0)
    )
    target_hours = float(
        project.get("target_hours", 0)
    )

    if target_hours <= 0:
        remaining = 0.0
        progress = 0.0
    else:
        remaining = max(
            0.0,
            round(target_hours - hours, 1),
        )
        progress = round(
            hours / target_hours * 100,
            1,
        )

    return {
        "hours": hours,
        "target_hours": target_hours,
        "remaining": remaining,
        "progress": progress,
    }


def project_progress(object_name):
    state = project_state(object_name)

    if state is None:
        return 0

    return state["progress"]


def project_remaining_hours(object_name):
    state = project_state(object_name)

    if state is None:
        return None

    return state["remaining"]