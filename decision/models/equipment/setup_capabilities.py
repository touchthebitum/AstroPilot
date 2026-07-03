from dataclasses import dataclass


@dataclass(frozen=True)
class SetupCapabilities:
    """
    Physical capabilities derived from an imaging setup.
    """

    sampling_arcsec_per_pixel: float

    field_width_deg: float | None = None
    field_height_deg: float | None = None

    limiting_resolution_arcsec: float | None = None