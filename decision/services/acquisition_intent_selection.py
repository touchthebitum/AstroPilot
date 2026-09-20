"""Select from precomputed intent eligibility and pairwise preference."""

from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityAssessment,
    AcquisitionIntentEligibilityStatus,
)
from decision.models.acquisition_intent_preference import (
    AcquisitionIntentPreference,
    AcquisitionIntentPreferenceStatus,
)
from decision.models.acquisition_intent_selection import (
    MULTIPLE_NON_DOMINATED_INTENTS,
    NO_ELIGIBLE_INTENT,
    ONLY_ELIGIBLE_INTENT,
    UNIQUE_NON_DOMINATED_INTENT,
    AcquisitionIntentSelection,
    AcquisitionIntentSelectionStatus,
)


class AcquisitionIntentSelectionError(ValueError):
    """Raised when the supplied pairwise preference graph is invalid."""


def select_acquisition_intent(
    eligibility_assessments: tuple[
        AcquisitionIntentEligibilityAssessment, ...
    ],
    pairwise_preferences: tuple[AcquisitionIntentPreference, ...],
) -> AcquisitionIntentSelection:
    """Select the Pareto frontier from authoritative precomputed inputs.

    Viable IDs are lexically ordered by their exact value solely to make the
    output independent of input iteration order.  That order has no preference
    or tie-breaking meaning.
    """

    _validate_collection_types(eligibility_assessments, pairwise_preferences)

    assessment_ids = [
        assessment.acquisition_intent_id
        for assessment in eligibility_assessments
    ]
    if len(set(assessment_ids)) != len(assessment_ids):
        raise AcquisitionIntentSelectionError(
            "duplicate acquisition-intent eligibility assessment"
        )

    eligible_ids = {
        assessment.acquisition_intent_id
        for assessment in eligibility_assessments
        if assessment.status is AcquisitionIntentEligibilityStatus.ELIGIBLE
    }
    ordered_eligible_ids = tuple(sorted(eligible_ids))
    expected_pairs = {
        frozenset((left_id, right_id))
        for index, left_id in enumerate(ordered_eligible_ids)
        for right_id in ordered_eligible_ids[index + 1 :]
    }
    supplied_pairs: set[frozenset[str]] = set()
    dominated_ids: set[str] = set()
    dominance_edges = {intent_id: set() for intent_id in eligible_ids}

    for preference in pairwise_preferences:
        left_id = preference.left_acquisition_intent_id
        right_id = preference.right_acquisition_intent_id
        if left_id == right_id:
            raise AcquisitionIntentSelectionError(
                "self acquisition-intent preference is not allowed"
            )
        for intent_id in (left_id, right_id):
            if intent_id not in assessment_ids:
                raise AcquisitionIntentSelectionError(
                    "preference references an intent absent from eligibility "
                    "assessments"
                )
            if intent_id not in eligible_ids:
                raise AcquisitionIntentSelectionError(
                    "preference references a non-eligible intent"
                )

        pair = frozenset((left_id, right_id))
        if pair in supplied_pairs:
            raise AcquisitionIntentSelectionError(
                "duplicate or contradictory acquisition-intent preference"
            )
        supplied_pairs.add(pair)

        if preference.status is AcquisitionIntentPreferenceStatus.LEFT_PREFERRED:
            dominated_ids.add(right_id)
            dominance_edges[left_id].add(right_id)
        elif (
            preference.status
            is AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED
        ):
            dominated_ids.add(left_id)
            dominance_edges[right_id].add(left_id)

    if supplied_pairs != expected_pairs:
        raise AcquisitionIntentSelectionError(
            "pairwise preferences must cover every eligible intent pair exactly once"
        )
    if _has_dominance_cycle(dominance_edges):
        raise AcquisitionIntentSelectionError(
            "pairwise preference dominance graph contains a cycle"
        )

    if not eligible_ids:
        return AcquisitionIntentSelection(
            selected_acquisition_intent_id=None,
            viable_acquisition_intent_ids=(),
            status=AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT,
            reason_codes=(NO_ELIGIBLE_INTENT,),
        )
    if len(eligible_ids) == 1:
        selected_id = ordered_eligible_ids[0]
        return AcquisitionIntentSelection(
            selected_acquisition_intent_id=selected_id,
            viable_acquisition_intent_ids=(selected_id,),
            status=AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
            reason_codes=(ONLY_ELIGIBLE_INTENT,),
        )

    non_dominated_ids = tuple(sorted(eligible_ids - dominated_ids))
    if not non_dominated_ids:
        raise AcquisitionIntentSelectionError(
            "pairwise preference cycle leaves no non-dominated intent"
        )
    if len(non_dominated_ids) == 1:
        selected_id = non_dominated_ids[0]
        return AcquisitionIntentSelection(
            selected_acquisition_intent_id=selected_id,
            viable_acquisition_intent_ids=(selected_id,),
            status=AcquisitionIntentSelectionStatus.PREFERRED,
            reason_codes=(UNIQUE_NON_DOMINATED_INTENT,),
        )
    return AcquisitionIntentSelection(
        selected_acquisition_intent_id=None,
        viable_acquisition_intent_ids=non_dominated_ids,
        status=AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE,
        reason_codes=(MULTIPLE_NON_DOMINATED_INTENTS,),
    )


def _validate_collection_types(
    eligibility_assessments: object,
    pairwise_preferences: object,
) -> None:
    if not isinstance(eligibility_assessments, tuple) or not all(
        isinstance(assessment, AcquisitionIntentEligibilityAssessment)
        for assessment in eligibility_assessments
    ):
        raise TypeError(
            "eligibility_assessments must be a tuple of "
            "AcquisitionIntentEligibilityAssessment"
        )
    if not isinstance(pairwise_preferences, tuple) or not all(
        isinstance(preference, AcquisitionIntentPreference)
        for preference in pairwise_preferences
    ):
        raise TypeError(
            "pairwise_preferences must be a tuple of AcquisitionIntentPreference"
        )


def _has_dominance_cycle(dominance_edges: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(intent_id: str) -> bool:
        if intent_id in visiting:
            return True
        if intent_id in visited:
            return False
        visiting.add(intent_id)
        if any(visit(dominated_id) for dominated_id in dominance_edges[intent_id]):
            return True
        visiting.remove(intent_id)
        visited.add(intent_id)
        return False

    return any(visit(intent_id) for intent_id in dominance_edges)
