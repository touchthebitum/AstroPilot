import ast
from pathlib import Path

import pytest

from decision.models.acquisition_intent_preference import (
    LUNAR_CONTAMINATION_EQUIVALENT,
    LUNAR_CONTAMINATION_INCOMPARABLE,
    LOWER_LUNAR_CONTAMINATION,
    AcquisitionIntentPreferenceStatus as PreferenceStatus,
)
from decision.models.lunar_contamination_comparison import (
    LunarContaminationComparison,
    LunarContaminationComparisonStatus as ComparisonStatus,
)
from decision.services.acquisition_intent_preference import (
    determine_acquisition_intent_preference,
)


def _comparison(status: ComparisonStatus) -> LunarContaminationComparison:
    return LunarContaminationComparison(
        left_filter_profile_id="left-profile",
        right_filter_profile_id="right-profile",
        status=status,
    )


@pytest.mark.parametrize(
    ("comparison_status", "preference_status", "reason_code"),
    [
        (
            ComparisonStatus.DOMINATES,
            PreferenceStatus.LEFT_PREFERRED,
            LOWER_LUNAR_CONTAMINATION,
        ),
        (
            ComparisonStatus.DOMINATED,
            PreferenceStatus.RIGHT_PREFERRED,
            LOWER_LUNAR_CONTAMINATION,
        ),
        (
            ComparisonStatus.EQUIVALENT,
            PreferenceStatus.NO_CLEAR_PREFERENCE,
            LUNAR_CONTAMINATION_EQUIVALENT,
        ),
        (
            ComparisonStatus.INCOMPARABLE,
            PreferenceStatus.NO_CLEAR_PREFERENCE,
            LUNAR_CONTAMINATION_INCOMPARABLE,
        ),
    ],
)
def test_maps_only_the_precomputed_comparison(
    comparison_status,
    preference_status,
    reason_code,
):
    result = determine_acquisition_intent_preference(
        "left-intent",
        "right-intent",
        _comparison(comparison_status),
    )

    assert result.status is preference_status
    assert result.reason_codes == (reason_code,)


@pytest.mark.parametrize(
    ("forward_status", "reverse_status"),
    [
        (ComparisonStatus.DOMINATES, ComparisonStatus.DOMINATED),
        (ComparisonStatus.DOMINATED, ComparisonStatus.DOMINATES),
        (ComparisonStatus.EQUIVALENT, ComparisonStatus.EQUIVALENT),
        (ComparisonStatus.INCOMPARABLE, ComparisonStatus.INCOMPARABLE),
    ],
)
def test_reversing_intents_and_comparison_is_symmetric(
    forward_status,
    reverse_status,
):
    forward = determine_acquisition_intent_preference(
        "left-intent",
        "right-intent",
        _comparison(forward_status),
    )
    reverse = determine_acquisition_intent_preference(
        "right-intent",
        "left-intent",
        _comparison(reverse_status),
    )

    inverse = {
        PreferenceStatus.LEFT_PREFERRED: PreferenceStatus.RIGHT_PREFERRED,
        PreferenceStatus.RIGHT_PREFERRED: PreferenceStatus.LEFT_PREFERRED,
        PreferenceStatus.NO_CLEAR_PREFERENCE: (
            PreferenceStatus.NO_CLEAR_PREFERENCE
        ),
    }
    assert reverse.status is inverse[forward.status]
    assert reverse.reason_codes == forward.reason_codes
    assert reverse.left_acquisition_intent_id == "right-intent"
    assert reverse.right_acquisition_intent_id == "left-intent"


def test_intent_ids_are_preserved_without_using_filter_profile_ids():
    result = determine_acquisition_intent_preference(
        " exact left intent ",
        " exact right intent ",
        _comparison(ComparisonStatus.DOMINATES),
    )

    assert result.left_acquisition_intent_id == " exact left intent "
    assert result.right_acquisition_intent_id == " exact right intent "


@pytest.mark.parametrize("comparison", [None, object(), "dominates"])
def test_rejects_invalid_comparison_type(comparison):
    with pytest.raises(TypeError, match="lunar_contamination_comparison"):
        determine_acquisition_intent_preference("left", "right", comparison)


def test_service_dependencies_are_limited_to_the_two_domain_models():
    source_path = (
        Path(__file__).parents[2]
        / "decision"
        / "services"
        / "acquisition_intent_preference.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {
        "decision.models.acquisition_intent_preference",
        "decision.models.lunar_contamination_comparison",
    }


def test_service_has_no_scoring_recalculation_or_out_of_scope_dependency():
    source_path = (
        Path(__file__).parents[2]
        / "decision"
        / "services"
        / "acquisition_intent_preference.py"
    )
    source = source_path.read_text(encoding="utf-8").lower()
    forbidden_terms = (
        "lunarcontaminationestimator",
        "intentnightevidence",
        "filteropticalprofileresolver",
        "projectacquisitionintenttarget",
        "target_hours",
        "acquired_hours",
        "productive_window",
        "weather",
        "seeing",
        "transparency",
        "user_priority",
        "project_priority",
        "lunar_source_factor",
        "rayleigh",
        "mie",
        "score",
        "weight",
        "ranking",
        "recommendation",
    )
    assert all(term not in source for term in forbidden_terms)
