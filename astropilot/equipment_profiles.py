import math
import json
import math
from pathlib import Path

json_path = Path(__file__).parent / "equipment_profiles.json"

with open(json_path, "r", encoding="utf-8") as f:
    EQUIPMENT_PROFILES = json.load(f)

CURRENT_EQUIPMENT = "redcat51_asi2600"
EQUIPMENT_PROFILES = {
    "redcat51_2600": {
        "name": "RedCat 51 + ASI2600MC",
        "focal_length_mm": 250,
        "sensor_width_mm": 23.5,
        "sensor_height_mm": 15.7,
        "pixel_size_mm": 3.76,
    },
    "evostar72_533": {
        "name": "Evostar 72ED + ASI533MC",
        "focal_length_mm": 420,
        "sensor_width_mm": 11.3,
        "sensor_height_mm": 11.3,
        "pixel_size_mm": 3.76,
    },
    "c8_hyperstar_2600": {
        "name": "C8 HyperStar + ASI2600MC",
        "pixel_size_mm": 3.76,
        "focal_length_mm": 390,
        "sensor_width_mm": 23.5,
        "sensor_height_mm": 15.7,
    },
    "rc8_294": {
        "name": "RC8 + ASI294MC",
        "focal_length_mm": 1625,
        "sensor_width_mm": 19.1,
        "sensor_height_mm": 13.0,
        "pixel_size_mm": 4.63,
    },

    "samyang135_2600": {
        "name": "Samyang 135 + ASI2600",
        "focal_length_mm": 135,
        "sensor_width_mm": 23.5,
        "sensor_height_mm": 15.7,
        "pixel_size_mm": 3.76,
    },
}

CURRENT_EQUIPMENT = "samyang135_2600"


def field_of_view_deg(focal_length_mm, sensor_mm):
    return 2 * math.degrees(
        math.atan(sensor_mm / (2 * focal_length_mm))
    )


def get_current_equipment():
    return EQUIPMENT_PROFILES[CURRENT_EQUIPMENT]


def get_fov(equipment=None):
    if equipment is None:
        equipment = get_current_equipment()

    return {
        "width_deg": field_of_view_deg(
            equipment["focal_length_mm"],
            equipment["sensor_width_mm"]
        ),
        "height_deg": field_of_view_deg(
            equipment["focal_length_mm"],
            equipment["sensor_height_mm"]
        ),
        }
def compare_object_to_equipment(object_size_arcmin, object_type="unknown", object_scale="medium", equipment=None):
    if equipment is None:
        equipment = get_current_equipment()

    fov = get_fov(equipment)
    width = fov["width_deg"]
    height = fov["height_deg"]
    frame_diag = math.sqrt(width ** 2 + height ** 2)


    focal_mm = equipment.get("focal_length_mm")
    pixel_um = equipment.get("pixel_size_um") or equipment.get("pixel_size_mm")

    if focal_mm and pixel_um:
        arcsec_pixel = round(206.265 * pixel_um / focal_mm, 2)
    else:
        arcsec_pixel = None

    object_size_deg = object_size_arcmin / 60
    ratio = object_size_deg / frame_diag

    print("DEBUG SCALE =", object_type, object_scale)

    if object_type == "planetary_nebula":
        ideal_min, ideal_max = 0.02, 0.20

    elif object_type == "galaxy":
        if object_scale == "huge":
            ideal_min, ideal_max = 0.08, 0.45
        elif object_scale == "small":
            ideal_min, ideal_max = 0.03, 0.18
        elif object_scale == "tiny":
            ideal_min, ideal_max = 0.015, 0.12
        else:
            ideal_min, ideal_max = 0.08, 0.25
        
    elif object_type == "cluster":
        ideal_min, ideal_max = 0.10, 0.60
    elif object_type == "nebula":
        if object_scale == "huge":
            ideal_min, ideal_max = 0.05, 0.45
        elif object_scale == "large":
            ideal_min, ideal_max = 0.08, 0.55
        else:
            ideal_min, ideal_max = 0.15, 0.60

    if ideal_min <= ratio <= ideal_max:
        score = 100
    elif ratio < ideal_min:
        score = 100 * (ratio / ideal_min)
    else:
        score = 100 * (ideal_max / ratio)

    score = max(0, min(100, round(score)))
    frame_bonus = round((score - 50) / 10)

    if object_type == "galaxy":
        if object_scale == "tiny":
            resolution_weight = 0.80
        elif object_scale == "small":
            resolution_weight = 0.70
        elif object_scale == "medium":
            resolution_weight = 0.60
        else:
            resolution_weight = 0.40

    elif object_type == "planetary_nebula":
        resolution_weight = 0.70

    elif object_type == "cluster":
        resolution_weight = 0.35

    else:   # nebula
        resolution_weight = 0.10

    framing_weight = 1 - resolution_weight
    res_score = resolution_score(arcsec_pixel, object_type, object_scale)
    combined_score =round(
        framing_weight * score + resolution_weight * res_score)
    

    return {
        "equipment_score": score,
        "frame_bonus": frame_bonus,
        "ratio": round(ratio, 3),
        "object_size_deg": round(object_size_deg, 2),
        "frame_diag_deg": round(frame_diag, 2),
        "arcsec_pixel": arcsec_pixel,
        "resolution_score": res_score,
        "combined_score": combined_score,
        "resolution_weight": resolution_weight,
        "framing_weight": framing_weight,
    }
def resolution_score(arcsec_pixel, object_type="unknown", object_scale="medium"):
    """
    Score 0-100 basé sur l'échantillonnage.
    """

    if arcsec_pixel is None:
        return 50

    if object_type == "planetary_nebula":
        ideal = 0.8

    elif object_type == "galaxy":
        if object_scale == "tiny":
            ideal = 0.6
        elif object_scale == "small":
            ideal = 0.8
        else:
            ideal = 1.2

    elif object_type == "cluster":
        ideal = 2.0

    elif object_type == "nebula":
        ideal = 3.0

    else:
        ideal = 2.0

    score = 100 * min(ideal / arcsec_pixel,
                      arcsec_pixel / ideal)

    print(
        "RESDEBUG",
        object_type,
        arcsec_pixel,
        score
    )

    return max(0, min(100, round(score)))

def equipment_match_score(object_size_arcmin, object_type="unknown", equipment=None):
    """
    Score d'adéquation entre un objet et le champ du matériel.
    Retourne un score entre 0 et 100.
    """

    if equipment is None:
        equipment = get_current_equipment()

    fov = get_fov(equipment)
    width = fov["width_deg"]
    height = fov["height_deg"]
    frame_diag = math.sqrt(width ** 2 + height ** 2)

    object_size_deg = object_size_arcmin / 60
    ratio = object_size_deg / frame_diag

    if object_type == "planetary_nebula":
        ideal_min = 0.02
        ideal_max = 0.20
    elif object_type == "galaxy":
        ideal_min = 0.08
        ideal_max = 0.25
    elif object_type == "cluster":
        ideal_min = 0.10
        ideal_max = 0.60
    elif object_type == "nebula":
        ideal_min = 0.20
        ideal_max = 0.60
    else:
        ideal_min = 0.15
        ideal_max = 0.90

    if ideal_min <= ratio <= ideal_max:
        return 100

    if ratio < ideal_min:
        score = 100 * (ratio / ideal_min)
    else:
        score = 100 * (ideal_max / ratio)

    return max(0, min(100, round(score)))

def set_current_equipment(profile_name):
    global CURRENT_EQUIPMENT

    if profile_name not in EQUIPMENT_PROFILES:
        raise ValueError(f"Profil inconnu : {profile_name}")

    CURRENT_EQUIPMENT = profile_name

def list_equipment():
    return list(EQUIPMENT_PROFILES.keys())
    
