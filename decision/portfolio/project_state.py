from __future__ import annotations

def project_state(object_name, projects):
    return project_state_from_project(projects.get(object_name))


def project_state_from_project(project):
    if project is None:
        return None

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


def project_progress(object_name, projects):
    state = project_state(object_name, projects)

    if state is None:
        return 0

    return state["progress"]


def project_remaining_hours(object_name, projects):
    state = project_state(object_name, projects)

    if state is None:
        return None

    return state["remaining"]
