import json
import math
import os
from pathlib import Path

from astropilot.equipment_catalog import EQUIPMENT_PROFILES

DATA_DIR = Path(__file__).parent.parent / "data"


class UserProfileError(Exception):
    pass


PROFILE_CONTAINER_TYPES = {
    "available_equipment": (list, "liste"),
    "preferences": (dict, "objet JSON"),
    "projects": (dict, "objet JSON"),
    "sessions": (list, "liste"),
    "location": (dict, "objet JSON"),
    "decision_weights": (dict, "objet JSON"),
}


def get_user_data_dir() -> Path:
    configured_dir = os.environ.get("ASTROPILOT_DATA_DIR")

    if configured_dir:
        return Path(configured_dir).expanduser()

    return DATA_DIR


def is_finite_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_user_profile(profile, profile_path: Path):
    if not isinstance(profile, dict):
        raise UserProfileError(
            f"Structure invalide dans {profile_path} : "
            "objet JSON attendu à la racine."
        )

    for field_name, (
        expected_type,
        expected_label,
    ) in PROFILE_CONTAINER_TYPES.items():
        if field_name not in profile:
            continue

        if not isinstance(profile[field_name], expected_type):
            raise UserProfileError(
                f"Champ '{field_name}' invalide dans "
                f"{profile_path} : {expected_label} attendu."
            )

    if "location" in profile:
        location = profile["location"]

        name = location.get("name")
        if not isinstance(name, str) or not name.strip():
            raise UserProfileError(
                f"Champ location.name invalide dans {profile_path} : "
                "chaîne non vide requise."
            )

        latitude = location.get("latitude")
        if not is_finite_number(latitude) or not -90 <= latitude <= 90:
            raise UserProfileError(
                f"Champ location.latitude invalide dans {profile_path} : "
                "nombre fini compris entre -90 et 90 requis."
            )

        longitude = location.get("longitude")
        if not is_finite_number(longitude) or not -180 <= longitude <= 180:
            raise UserProfileError(
                f"Champ location.longitude invalide dans {profile_path} : "
                "nombre fini compris entre -180 et 180 requis."
            )

    for index, equipment_name in enumerate(
        profile.get("available_equipment", [])
    ):
        if (
            not isinstance(equipment_name, str)
            or not equipment_name.strip()
        ):
            raise UserProfileError(
                f"Entrée available_equipment[{index}] invalide "
                f"dans {profile_path} : chaîne non vide attendue."
            )

    for project_name, project in profile.get("projects", {}).items():
        if not isinstance(project, dict):
            raise UserProfileError(
                f"Entrée projects[{project_name!r}] invalide dans "
                f"{profile_path} : objet JSON attendu."
            )

        for field_name in ("hours", "target_hours"):
            if field_name not in project:
                continue

            value = project[field_name]

            if not is_finite_number(value) or value < 0:
                raise UserProfileError(
                    f"Champ projects[{project_name!r}].{field_name} "
                    f"invalide dans {profile_path} : nombre fini "
                    "positif ou nul attendu."
                )

        if "filter_targets" not in project:
            continue

        filter_targets = project["filter_targets"]
        filter_targets_path = (
            f"projects[{project_name!r}].filter_targets"
        )

        if not isinstance(filter_targets, dict):
            raise UserProfileError(
                f"Champ {filter_targets_path} invalide dans "
                f"{profile_path} : objet JSON attendu."
            )

        for filter_name, target_hours in filter_targets.items():
            if (
                not isinstance(filter_name, str)
                or not filter_name.strip()
            ):
                raise UserProfileError(
                    f"Champ {filter_targets_path} invalide dans "
                    f"{profile_path} : nom de filtre non vide attendu."
                )

            if not is_finite_number(target_hours) or target_hours < 0:
                raise UserProfileError(
                    f"Champ {filter_targets_path}[{filter_name!r}] "
                    f"invalide dans {profile_path} : nombre fini "
                    "positif ou nul attendu."
                )

        if not filter_targets:
            continue

        if "target_hours" not in project:
            raise UserProfileError(
                f"Champ projects[{project_name!r}].target_hours "
                f"requis dans {profile_path} lorsque des objectifs "
                "par filtre sont configurés."
            )

        filter_hours = sum(filter_targets.values())
        target_hours = project["target_hours"]

        if not math.isclose(filter_hours, target_hours, abs_tol=0.01):
            raise UserProfileError(
                f"Champ {filter_targets_path} invalide dans "
                f"{profile_path} : somme {filter_hours:.2f} h "
                f"incompatible avec target_hours {target_hours:.2f} h."
            )

    for index, session in enumerate(profile.get("sessions", [])):
        if not isinstance(session, dict):
            raise UserProfileError(
                f"Entrée sessions[{index}] invalide dans "
                f"{profile_path} : objet JSON attendu."
            )

        object_name = session.get("object")
        if (
            not isinstance(object_name, str)
            or not object_name.strip()
        ):
            raise UserProfileError(
                f"Champ sessions[{index}].object invalide dans "
                f"{profile_path} : chaîne non vide attendue."
            )

        hours = session.get("hours")
        if not is_finite_number(hours) or hours <= 0:
            raise UserProfileError(
                f"Champ sessions[{index}].hours invalide dans "
                f"{profile_path} : nombre fini strictement "
                "positif attendu."
            )

        filter_type = session.get("filter_type")
        if filter_type is not None and (
            not isinstance(filter_type, str)
            or not filter_type.strip()
        ):
            raise UserProfileError(
                f"Champ sessions[{index}].filter_type invalide "
                f"dans {profile_path} : chaîne non vide ou null "
                "attendu."
            )

    active_equipment = profile.get("active_equipment")
    if (
        not isinstance(active_equipment, str)
        or not active_equipment.strip()
    ):
        raise UserProfileError(
            f"Champ active_equipment invalide dans {profile_path} : "
            "chaîne non vide requise."
        )

    available_equipment = profile.get("available_equipment", [])
    if active_equipment not in available_equipment:
        raise UserProfileError(
            f"Champ active_equipment invalide dans {profile_path} : "
            "doit figurer dans available_equipment."
        )

    for index, equipment_name in enumerate(available_equipment):
        if equipment_name not in EQUIPMENT_PROFILES:
            raise UserProfileError(
                f"Entrée available_equipment[{index}] invalide dans "
                f"{profile_path} : matériel inconnu "
                f"({equipment_name!r})."
            )

    return profile


def load_user_profile():
    profile_path = get_user_data_dir() / "user_profile.json"

    try:
        with profile_path.open("r", encoding="utf-8") as handle:
            profile = json.load(handle)
    except FileNotFoundError as exc:
        raise UserProfileError(
            f"Profil utilisateur introuvable : {profile_path}. "
            "Définissez ASTROPILOT_DATA_DIR vers un dossier "
            "contenant user_profile.json."
        ) from exc
    except json.JSONDecodeError as exc:
        raise UserProfileError(
            f"Profil utilisateur JSON invalide : {profile_path} "
            f"(ligne {exc.lineno}, colonne {exc.colno})."
        ) from exc

    return validate_user_profile(profile, profile_path)
    
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
    data_dir = get_user_data_dir()
    path = data_dir / "user_profile.json"
    temp_path = data_dir / "user_profile.json.tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(
            profile,
            f,
            indent=4,
            ensure_ascii=False,
        )

    temp_path.replace(path)


def record_session(
    project_name,
    hours,
    date,
    filter_type=None,
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

    session = {
        "date": date,
        "object": project_name,
        "hours": float(hours),
    }

    if filter_type is not None:
        session["filter_type"] = filter_type

    sessions.append(session)

    save_user_profile(profile)
