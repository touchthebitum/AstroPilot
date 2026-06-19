import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_user_profile():
    with open(DATA_DIR / "user_profile.json", "r") as f:
        return json.load(f)
    
def get_active_equipment():
    return load_user_profile().get("active_equipment")


def get_available_equipment():
    return load_user_profile().get("available_equipment", [])

def get_preferences():
    return load_user_profile().get("preferences", {})

def get_projects():
    return load_user_profile().get("projects", {})

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