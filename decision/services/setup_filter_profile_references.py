from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.services.filter_optical_profile_resolver import (
    FilterOpticalProfileResolutionError,
    FilterOpticalProfileResolver,
)


class SetupFilterProfileReferenceValidationError(ValueError):
    """Raised when a setup references an unusable filter profile."""


def validate_setup_filter_profile_references(
    capabilities: SetupFilterCapabilities,
    resolver: FilterOpticalProfileResolver,
) -> None:
    """Validate exact physical profile references against setup semantics."""

    if not isinstance(capabilities, SetupFilterCapabilities):
        raise TypeError("capabilities must be SetupFilterCapabilities")
    if not isinstance(resolver, FilterOpticalProfileResolver):
        raise TypeError("resolver must be FilterOpticalProfileResolver")

    for filter_profile_id in capabilities.available_filter_profile_ids:
        try:
            profile = resolver.resolve(filter_profile_id)
        except FilterOpticalProfileResolutionError as error:
            raise SetupFilterProfileReferenceValidationError(
                f"unresolvable filter_profile_id: {filter_profile_id}"
            ) from error

        if profile.filter_type not in capabilities.available_filter_types:
            raise SetupFilterProfileReferenceValidationError(
                "filter profile type is not available on setup: "
                f"{filter_profile_id} ({profile.filter_type})"
            )
