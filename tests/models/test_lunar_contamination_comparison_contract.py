from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.lunar_contamination_comparison import (
    LunarContaminationComparison,
    LunarContaminationComparisonStatus,
)


def _comparison(**overrides) -> LunarContaminationComparison:
    values = {
        "left_filter_profile_id": "baader_ha_highspeed_6_5nm",
        "right_filter_profile_id": "baader_oiii_highspeed_6_5nm",
        "status": LunarContaminationComparisonStatus.DOMINATES,
    }
    values.update(overrides)
    return LunarContaminationComparison(**values)


def test_result_contract_is_exact_immutable_and_preserves_ids():
    comparison = _comparison(
        left_filter_profile_id=" left-profile ",
        right_filter_profile_id=" right-profile ",
    )

    assert tuple(field.name for field in fields(comparison)) == (
        "left_filter_profile_id",
        "right_filter_profile_id",
        "status",
    )
    assert comparison.left_filter_profile_id == " left-profile "
    assert comparison.right_filter_profile_id == " right-profile "
    with pytest.raises((FrozenInstanceError, AttributeError)):
        comparison.status = LunarContaminationComparisonStatus.EQUIVALENT


def test_status_contract_has_exactly_the_four_directional_values():
    assert tuple(LunarContaminationComparisonStatus) == (
        LunarContaminationComparisonStatus.DOMINATES,
        LunarContaminationComparisonStatus.DOMINATED,
        LunarContaminationComparisonStatus.EQUIVALENT,
        LunarContaminationComparisonStatus.INCOMPARABLE,
    )


@pytest.mark.parametrize(
    "field_name",
    ["left_filter_profile_id", "right_filter_profile_id"],
)
@pytest.mark.parametrize("value", [None, 42, "", "   "])
def test_rejects_invalid_profile_ids(field_name, value):
    with pytest.raises((TypeError, ValueError), match=field_name):
        _comparison(**{field_name: value})


@pytest.mark.parametrize("status", [None, "dominates", 1])
def test_rejects_invalid_status(status):
    with pytest.raises(TypeError, match="status"):
        _comparison(status=status)
