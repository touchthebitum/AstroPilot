from dataclasses import dataclass


@dataclass(frozen=True)
class Camera:
    """
    Represents an imaging camera.
    """

    manufacturer: str
    model: str

    pixel_size_um: float

    sensor_width_px: int
    sensor_height_px: int

    monochrome: bool
