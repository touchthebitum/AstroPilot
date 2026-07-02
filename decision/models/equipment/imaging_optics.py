from dataclasses import dataclass


@dataclass(frozen=True)
class Optics:
    """
    Represents the main imaging optics.
    """

    manufacturer: str
    model: str

    focal_length_mm: float
    aperture_mm: float

    focal_ratio: float | None = None