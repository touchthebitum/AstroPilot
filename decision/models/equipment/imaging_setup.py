from dataclasses import dataclass

from decision.models.equipment.camera import Camera
from decision.models.equipment.mount import Mount
from decision.models.equipment.imaging_optics import ImagingOptics
from decision.models.equipment.imaging_filter import ImagingFilter


@dataclass(frozen=True)
class ImagingSetup:
    """
    Represents the complete imaging setup used during a session.
    """

    mount: Mount
    optics: ImagingOptics
    camera: Camera

    filter: ImagingFilter | None = None
