from dataclasses import dataclass

from decision.models.equipment.imaging_setup import ImagingSetup


@dataclass(frozen=True)
class EquipmentContext:
    """
    Equipment available for the current decision.
    """

    setup: ImagingSetup