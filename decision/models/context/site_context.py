from  dataclasses import dataclass

@dataclass(frozen=True)
class SiteContext:
    """
    Describes the observing site.
    """

    name: str
    latitude: float
    longitude: float
    elevation: float

    bortle: int

    timezone: str = "Europe/Zurich"

    sqm: float | None = None

    has_horizon_profile: bool = False
