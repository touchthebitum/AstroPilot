"""Preference between eligible intents from a precomputed lunar comparison."""

from decision.models.acquisition_intent_preference import (
    LUNAR_CONTAMINATION_EQUIVALENT,
    LUNAR_CONTAMINATION_INCOMPARABLE,
    LOWER_LUNAR_CONTAMINATION,
    AcquisitionIntentPreference,
    AcquisitionIntentPreferenceStatus,
)
from decision.models.lunar_contamination_comparison import (
    LunarContaminationComparison,
    LunarContaminationComparisonStatus,
)


_PREFERENCE_BY_COMPARISON = {
    LunarContaminationComparisonStatus.DOMINATES: (
        AcquisitionIntentPreferenceStatus.LEFT_PREFERRED,
        LOWER_LUNAR_CONTAMINATION,
    ),
    LunarContaminationComparisonStatus.DOMINATED: (
        AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED,
        LOWER_LUNAR_CONTAMINATION,
    ),
    LunarContaminationComparisonStatus.EQUIVALENT: (
        AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE,
        LUNAR_CONTAMINATION_EQUIVALENT,
    ),
    LunarContaminationComparisonStatus.INCOMPARABLE: (
        AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE,
        LUNAR_CONTAMINATION_INCOMPARABLE,
    ),
}


def determine_acquisition_intent_preference(
    left_acquisition_intent_id: str,
    right_acquisition_intent_id: str,
    lunar_contamination_comparison: LunarContaminationComparison,
) -> AcquisitionIntentPreference:
    """Prefer between two intents that callers have already found eligible.

    The supplied comparison is authoritative: this service neither recalculates
    lunar contamination nor infers intent identities from filter-profile IDs.
    """

    if not isinstance(
        lunar_contamination_comparison,
        LunarContaminationComparison,
    ):
        raise TypeError(
            "lunar_contamination_comparison must be a "
            "LunarContaminationComparison"
        )

    status, reason_code = _PREFERENCE_BY_COMPARISON[
        lunar_contamination_comparison.status
    ]
    return AcquisitionIntentPreference(
        left_acquisition_intent_id=left_acquisition_intent_id,
        right_acquisition_intent_id=right_acquisition_intent_id,
        status=status,
        reason_codes=(reason_code,),
    )
