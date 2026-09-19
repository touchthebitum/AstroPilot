from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.services.setup_filter_capabilities_resolver import (
    SetupFilterCapabilitiesResolver,
)


SETUP_FILTER_CAPABILITIES: tuple[SetupFilterCapabilities, ...] = (
    SetupFilterCapabilities(
        equipment_id="samyang_183",
        available_filter_types=("Ha", "OIII", "SII", "L", "R", "G", "B"),
    ),
)


def build_production_setup_filter_capabilities_resolver(
) -> SetupFilterCapabilitiesResolver:
    return SetupFilterCapabilitiesResolver(SETUP_FILTER_CAPABILITIES)
