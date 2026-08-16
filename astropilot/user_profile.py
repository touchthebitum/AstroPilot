import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_user_profile():
    with open(DATA_DIR / "user_profile.json", "r") as f:
        return json.load(f)
    
def get_decision_weights():

    profile = load_user_profile()
    prefs = profile.get("preferences", {})

    mode = prefs.get("decision_mode", "balanced")

    if mode == "science":
        return 0.8, 0.2

    elif mode == "finisher":
        return 0.5, 0.5

    return 0.7, 0.30
    
def get_active_equipment():
    return load_user_profile().get("active_equipment")


def get_available_equipment():
    return load_user_profile().get("available_equipment", [])

def get_preferences():
    return load_user_profile().get("preferences", {})

def get_projects():
    return load_user_profile().get("projects", {})

def get_rule_weights():
    profile = load_user_profile()
    return profile.get("decision_weights", {})

def load_locations():
    with open(DATA_DIR / "locations.json", "r") as f:
        return json.load(f)

def get_default_location():
    profile = load_user_profile()
    return profile.get("location", {
        "name": "Buttes",
        "latitude": 46.7508,
        "longitude": 6.5495
    })

def favorite_targets():
    return (
        load_user_profile()
        .get("preferences", {})
        .get("favorite_targets", ["galaxy", "nebula"])
    )

def save_user_profile(profile):
    path = DATA_DIR / "user_profile.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            profile,
            f,
            indent=4,
            ensure_ascii=False,
        )


def record_session(
    project_name,
    hours,
    date,
):
    if hours <= 0:
        raise ValueError("hours must be positive")

    profile = load_user_profile()
    projects = profile.get("projects", {})

    if project_name not in projects:
        raise ValueError(
            f"Unknown project: {project_name}"
        )

    project = projects[project_name]

    current_hours = float(
        project.get("hours", 0)
    )
    target_hours = float(
        project.get("target_hours", 0)
    )

    new_hours = current_hours + float(hours)

    if target_hours > 0:
        new_hours = min(
            new_hours,
            target_hours,
        )

    project["hours"] = new_hours

    sessions = profile.setdefault(
        "sessions",
        [],
    )

    sessions.append(
        {
            "date": date,
            "object": project_name,
            "hours": float(hours),
        }
    )

    save_user_profile(profile)
