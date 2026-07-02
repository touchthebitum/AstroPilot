from dataclasses import dataclass

from decision.models.sky.celestial_object import CelestialObject


@dataclass(frozen=True)
class SkyContext:
    """
    Describes the sky conditions relevant to the current decision.
    """

    target: CelestialObject

    moon_illumination: float
    moon_separation_deg: float

    target_altitude_deg: float

    astronomical_darkness: bool
