import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from decision.models.acquisition_intent_eligibility import (
    AcquisitionIntentEligibilityAssessment,
    AcquisitionIntentEligibilityReason,
    AcquisitionIntentEligibilityStatus,
)
from decision.models.acquisition_intent_preference import (
    LUNAR_CONTAMINATION_EQUIVALENT,
    LOWER_LUNAR_CONTAMINATION,
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
from decision.services.acquisition_intent_selection import (
    AcquisitionIntentSelectionError,
    select_acquisition_intent,
)


def _eligible(intent_id: str) -> AcquisitionIntentEligibilityAssessment:
    return AcquisitionIntentEligibilityAssessment(
        intent_id,
        AcquisitionIntentEligibilityStatus.ELIGIBLE,
        (),
        (),
    )


def _not_eligible(intent_id: str) -> AcquisitionIntentEligibilityAssessment:
    return AcquisitionIntentEligibilityAssessment(
        intent_id,
        AcquisitionIntentEligibilityStatus.NOT_ELIGIBLE,
        (AcquisitionIntentEligibilityReason.REQUIRED_FILTER_UNAVAILABLE,),
        (),
    )


def _preference(
    left_id: str,
    right_id: str,
    status: AcquisitionIntentPreferenceStatus,
) -> AcquisitionIntentPreference:
    reason = (
        LUNAR_CONTAMINATION_EQUIVALENT
        if status is AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
        else LOWER_LUNAR_CONTAMINATION
    )
    return AcquisitionIntentPreference(left_id, right_id, status, (reason,))


def _select(assessments=(), preferences=()):
    return select_acquisition_intent(assessments, preferences)


def test_selection_model_is_validated_and_immutable():
    result = AcquisitionIntentSelection(
        "intent",
        ("intent",),
        AcquisitionIntentSelectionStatus.PREFERRED,
        (UNIQUE_NON_DOMINATED_INTENT,),
    )

    with pytest.raises(FrozenInstanceError):
        result.status = AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE
    with pytest.raises(ValueError):
        AcquisitionIntentSelection(
            None,
            ("intent",),
            AcquisitionIntentSelectionStatus.PREFERRED,
            (UNIQUE_NON_DOMINATED_INTENT,),
        )


def test_no_eligible_intent():
    result = _select((_not_eligible("A"),))

    assert result == AcquisitionIntentSelection(
        None,
        (),
        AcquisitionIntentSelectionStatus.NO_ELIGIBLE_INTENT,
        (NO_ELIGIBLE_INTENT,),
    )


def test_only_eligible_intent_is_selected():
    result = _select((_eligible("A"),))

    assert result == AcquisitionIntentSelection(
        "A",
        ("A",),
        AcquisitionIntentSelectionStatus.SINGLE_ELIGIBLE_INTENT,
        (ONLY_ELIGIBLE_INTENT,),
    )


@pytest.mark.parametrize(
    ("status", "selected"),
    [
        (AcquisitionIntentPreferenceStatus.LEFT_PREFERRED, "A"),
        (AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED, "B"),
    ],
)
def test_two_intents_with_a_preference_select_the_preferred_side(
    status,
    selected,
):
    result = _select(
        (_eligible("A"), _eligible("B")),
        (_preference("A", "B", status),),
    )

    assert result.selected_acquisition_intent_id == selected
    assert result.viable_acquisition_intent_ids == (selected,)
    assert result.status is AcquisitionIntentSelectionStatus.PREFERRED


def test_two_intents_without_clear_preference_remain_viable():
    result = _select(
        (_eligible("B"), _eligible("A")),
        (
            _preference(
                "B",
                "A",
                AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE,
            ),
        ),
    )

    assert result.selected_acquisition_intent_id is None
    assert result.viable_acquisition_intent_ids == ("A", "B")
    assert result.reason_codes == (MULTIPLE_NON_DOMINATED_INTENTS,)


def test_three_intents_leave_a_and_c_non_dominated():
    result = _select(
        tuple(map(_eligible, ("A", "B", "C"))),
        (
            _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            _preference("C", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            _preference(
                "A", "C", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
            ),
        ),
    )

    assert result.viable_acquisition_intent_ids == ("A", "C")
    assert result.status is AcquisitionIntentSelectionStatus.NO_CLEAR_PREFERENCE


def test_one_intent_dominating_both_others_is_selected():
    result = _select(
        tuple(map(_eligible, ("A", "B", "C"))),
        (
            _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            _preference("A", "C", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            _preference(
                "B", "C", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
            ),
        ),
    )

    assert result.selected_acquisition_intent_id == "A"


def test_dominance_chain_selects_only_the_undominated_intent():
    result = _select(
        tuple(map(_eligible, ("A", "B", "C"))),
        (
            _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            _preference("A", "C", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            _preference("B", "C", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
        ),
    )

    assert result.viable_acquisition_intent_ids == ("A",)


def test_cycle_with_no_non_dominated_intent_fails_closed():
    with pytest.raises(AcquisitionIntentSelectionError, match="cycle"):
        _select(
            tuple(map(_eligible, ("A", "B", "C"))),
            (
                _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
                _preference("B", "C", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
                _preference("C", "A", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            ),
        )


def test_subcycle_fails_closed_even_with_a_non_dominated_outsider():
    with pytest.raises(AcquisitionIntentSelectionError, match="cycle"):
        _select(
            tuple(map(_eligible, ("A", "B", "C", "D"))),
            (
                _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
                _preference("B", "C", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
                _preference("C", "A", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
                _preference(
                    "A", "D", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
                ),
                _preference(
                    "B", "D", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
                ),
                _preference(
                    "C", "D", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
                ),
            ),
        )


def test_missing_pair_is_rejected():
    with pytest.raises(AcquisitionIntentSelectionError, match="cover"):
        _select(tuple(map(_eligible, ("A", "B", "C"))), ())


def test_duplicate_or_contradictory_pair_is_rejected():
    with pytest.raises(AcquisitionIntentSelectionError, match="duplicate"):
        _select(
            (_eligible("A"), _eligible("B")),
            (
                _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
                _preference("B", "A", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            ),
        )


def test_self_pair_is_rejected():
    with pytest.raises(AcquisitionIntentSelectionError, match="self"):
        _select(
            (_eligible("A"),),
            (
                _preference("A", "A", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            ),
        )


def test_pair_referencing_noneligible_intent_is_rejected():
    with pytest.raises(AcquisitionIntentSelectionError, match="non-eligible"):
        _select(
            (_eligible("A"), _not_eligible("B")),
            (
                _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            ),
        )


def test_pair_referencing_absent_intent_is_rejected():
    with pytest.raises(AcquisitionIntentSelectionError, match="absent"):
        _select(
            (_eligible("A"),),
            (
                _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            ),
        )


def test_duplicate_assessments_are_rejected():
    with pytest.raises(AcquisitionIntentSelectionError, match="duplicate"):
        _select((_eligible("A"), _eligible("A")))


@pytest.mark.parametrize(
    ("assessments", "preferences"),
    [([], ()), ((object(),), ()), ((), []), ((), (object(),))],
)
def test_bad_collection_or_member_types_are_rejected(
    assessments,
    preferences,
):
    with pytest.raises(TypeError):
        _select(assessments, preferences)


def test_output_is_deterministic_across_input_orders_and_pair_orientations():
    first = _select(
        tuple(map(_eligible, ("C", "A", "B"))),
        (
            _preference("A", "B", AcquisitionIntentPreferenceStatus.LEFT_PREFERRED),
            _preference(
                "C", "B", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
            ),
            _preference(
                "C", "A", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
            ),
        ),
    )
    second = _select(
        tuple(map(_eligible, ("B", "C", "A"))),
        (
            _preference(
                "A", "C", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
            ),
            _preference(
                "B", "C", AcquisitionIntentPreferenceStatus.NO_CLEAR_PREFERENCE
            ),
            _preference("B", "A", AcquisitionIntentPreferenceStatus.RIGHT_PREFERRED),
        ),
    )

    assert first == second
    assert first.viable_acquisition_intent_ids == ("A", "C")


def test_service_uses_only_precomputed_domain_results():
    source_path = (
        Path(__file__).parents[2]
        / "decision"
        / "services"
        / "acquisition_intent_selection.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {
        "decision.models.acquisition_intent_eligibility",
        "decision.models.acquisition_intent_preference",
        "decision.models.acquisition_intent_selection",
    }
    forbidden_terms = (
        "estimator",
        "lunar_contamination_comparison",
        "productive_window",
        "weather",
        "mission",
        "score",
        "wins",
        "ranking",
        "recommendation",
    )
    assert all(term not in source.lower() for term in forbidden_terms)
