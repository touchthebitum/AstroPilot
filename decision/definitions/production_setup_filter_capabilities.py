from decision.definitions.production_filter_optical_profiles import (
    build_production_filter_optical_profile_resolver,
)
from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.services.setup_filter_capabilities_resolver import (
    SetupFilterCapabilitiesResolver,
)
from decision.services.setup_filter_profile_references import (
    validate_setup_filter_profile_references,
)


SETUP_FILTER_CAPABILITIES: tuple[SetupFilterCapabilities, ...] = (
    SetupFilterCapabilities(
        equipment_id="samyang_183",
        available_filter_types=("Ha", "OIII", "SII", "L", "R", "G", "B"),
        available_filter_profile_ids=(
            "baader_ha_highspeed_6_5nm",
            "baader_oiii_highspeed_6_5nm",
            "baader_sii_highspeed_6_5nm",
        ),
    ),
)


def build_production_setup_filter_capabilities_resolver(
) -> SetupFilterCapabilitiesResolver:
    filter_optical_profile_resolver = (
        build_production_filter_optical_profile_resolver()
    )
    for capabilities in SETUP_FILTER_CAPABILITIES:
        validate_setup_filter_profile_references(
            capabilities,
            filter_optical_profile_resolver,
        )
    return SetupFilterCapabilitiesResolver(SETUP_FILTER_CAPABILITIES)
