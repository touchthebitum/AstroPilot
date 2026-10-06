import pytest

from decision.filtering.intent_filter_reconciliation import (
    reconcile_selected_filter,
    validate_selected_filter_for_intent,
)
from decision.filtering.selected_filter import SelectedFilter


@pytest.mark.parametrize(
    ("intent_id", "required_type", "other_type"),
    [("sh2-129_ha", "Ha", "OIII"), ("ou4_oiii", "OIII", "Ha")],
)
def test_divergence_rejected_without_mutating_user_default(intent_id, required_type, other_type):
    selected = SelectedFilter("Default", other_type, source="user_default")
    with pytest.raises(ValueError, match="^selected_filter_intent_mismatch$"):
        validate_selected_filter_for_intent(
            imaging_field_id="sh2-129_ou4", acquisition_intent_id=intent_id,
            selected_filter=selected,
        )
    assert selected.filter_type == other_type
    assert selected.source == "user_default"


@pytest.mark.parametrize("bandwidth_nm", [3.0, 7.0])
def test_compatible_selected_filter_preserved_exactly(bandwidth_nm):
    selected = SelectedFilter("Default", "Ha", bandwidth_nm, source="user_default")
    result = reconcile_selected_filter(
        imaging_field_id="sh2-129_ou4", acquisition_intent_id="sh2-129_ha",
        available_filters=(SelectedFilter("Other Ha", "Ha", 12.0),),
        selected_filter=selected,
    )
    assert result is selected
    validate_selected_filter_for_intent(
        imaging_field_id="sh2-129_ou4", acquisition_intent_id="sh2-129_ha",
        selected_filter=result,
    )


def test_unknown_intent_cannot_authorize_a_default_filter():
    with pytest.raises(ValueError, match="acquisition_intent_not_in_imaging_field"):
        reconcile_selected_filter(
            imaging_field_id="sh2-129_ou4", acquisition_intent_id="unknown",
            available_filters=(SelectedFilter("Ha", "Ha"),), selected_filter=None,
        )
