from dataclasses import dataclass


@dataclass(frozen=True)
class PreferencesContext:
    """
    Describes the user's decision preferences.
    """

    astro_weight: float

    project_weight: float

    minimum_altitude_deg: float

    minimum_sqm: float
