from dataclasses import dataclass


@dataclass(frozen=True)
class Filter:
    """
    Represents an astrophotography filter.
    """

    manufacturer: str
    name: str

    filter_type: str

    bandwidth_nm: float | None = None
    central_wavelength_nm: float | None = None