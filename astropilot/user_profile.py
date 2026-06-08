import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_user_profile():
    with open(DATA_DIR / "user_profile.json", "r") as f:
        return json.load(f)


def load_locations():
    with open(DATA_DIR / "locations.json", "r") as f:
        return json.load(f)


def get_default_location():
    profile = load_user_profile()
    locations = load_locations()

    location_id = profile["default_location"]

    for loc in locations:
        if loc["id"] == location_id:
            return loc

    raise ValueError(f"Localisation inconnue : {location_id}")

def favorite_targets():
    return load_user_profile()["preferences"]["favorite_targets"]
