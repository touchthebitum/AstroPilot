"""Resolve the exact setup filter profiles matching an acquisition intent."""

from decision.models.acquisition_intent_filter_profile_resolution import (
    AcquisitionIntentFilterProfileResolution,
    AcquisitionIntentFilterProfileResolutionStatus,
)
from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.models.imaging_field import AcquisitionIntent
from decision.services.filter_optical_profile_resolver import (
    FilterOpticalProfileResolutionError,
    FilterOpticalProfileResolver,
)


class AcquisitionIntentFilterProfileResolutionError(ValueError):
    """Raised when setup profile references cannot be resolved safely."""


def resolve_acquisition_intent_filter_profile(
    acquisition_intent: AcquisitionIntent,
    setup_filter_capabilities: SetupFilterCapabilities,
    resolver: FilterOpticalProfileResolver,
) -> AcquisitionIntentFilterProfileResolution:
    """Resolve exact matching profiles without ranking or fallback."""

    if not isinstance(acquisition_intent, AcquisitionIntent):
        raise TypeError("acquisition_intent must be AcquisitionIntent")
    if not isinstance(setup_filter_capabilities, SetupFilterCapabilities):
        raise TypeError(
            "setup_filter_capabilities must be SetupFilterCapabilities"
        )
    if not isinstance(
        resolver,
        FilterOpticalProfileResolver,
    ):
        raise TypeError("resolver must be FilterOpticalProfileResolver")

    matching_filter_profile_ids: list[str] = []
    for filter_profile_id in (
        setup_filter_capabilities.available_filter_profile_ids
    ):
        try:
            profile = resolver.resolve(filter_profile_id)
        except FilterOpticalProfileResolutionError as error:
            raise AcquisitionIntentFilterProfileResolutionError(
                f"unresolvable filter_profile_id: {filter_profile_id}"
            ) from error
        if profile.filter_type == acquisition_intent.filter_type:
            matching_filter_profile_ids.append(filter_profile_id)

    matches = tuple(matching_filter_profile_ids)
    if len(matches) == 1:
        status = AcquisitionIntentFilterProfileResolutionStatus.RESOLVED
    elif not matches:
        status = AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE
    else:
        status = AcquisitionIntentFilterProfileResolutionStatus.AMBIGUOUS

    return AcquisitionIntentFilterProfileResolution(
        acquisition_intent_id=acquisition_intent.acquisition_intent_id,
        status=status,
        matching_filter_profile_ids=matches,
    )
