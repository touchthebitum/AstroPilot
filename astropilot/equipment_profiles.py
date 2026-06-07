import math

CURRENT_EQUIPMENT = {
    "name": "RedCat 51 + ASI2600",

    "focal_length_mm": 250,

    "sensor_width_mm": 23.5,
    "sensor_height_mm": 15.7,
}


def field_of_view_deg(focal_length_mm, sensor_mm):
    return 2 * math.degrees(
        math.atan(sensor_mm / (2 * focal_length_mm))
    )


def get_fov(equipment):

    return {
        "width_deg": field_of_view_deg(
            equipment["focal_length_mm"],
            equipment["sensor_width_mm"]
        ),

        "height_deg": field_of_view_deg(
            equipment["focal_length_mm"],
            equipment["sensor_height_mm"]
        )
    }
