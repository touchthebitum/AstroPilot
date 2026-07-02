from dataclasses import dataclass


@dataclass(frozen=True)
class CelestialObject:
    """
    Represents an astronomical imaging target.
    """

    name: str
    object_type: str
    angular_size_arcmin: float