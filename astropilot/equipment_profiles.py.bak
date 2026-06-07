import math

EQUIPMENT_PROFILES = {
    "redcat51_2600": {
        "name": "RedCat 51 + ASI2600MC",
        "focal_length_mm": 250,
        "sensor_width_mm": 23.5,
        "sensor_height_mm": 15.7,
    },
    "evostar72_533": {
        "name": "Evostar 72ED + ASI533MC",
        "focal_length_mm": 420,
        "sensor_width_mm": 11.3,
        "sensor_height_mm": 11.3,
    },
    "c8_hyperstar_2600": {
        "name": "C8 HyperStar + ASI2600MC",
        "focal_length_mm": 390,
        "sensor_width_mm": 23.5,
        "sensor_height_mm": 15.7,
    },
    "rc8_294": {
        "name": "RC8 + ASI294MC",
        "focal_length_mm": 1625,
        "sensor_width_mm": 19.1,
        "sensor_height_mm": 13.0,
    },
}

CURRENT_EQUIPMENT = "redcat51_2600"


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
