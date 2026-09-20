from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.lunar_contamination_estimate import (
    LunarContaminationEstimate,
)


def _estimate(**overrides) -> LunarContaminationEstimate:
    values = {
        "filter_profile_id": "baader_oiii_highspeed_6_5nm",
        "lunar_source_factor": 0.5,
        "rayleigh_relative_index": 2.0,
        "mie_relative_index": 0.25,
    }
    values.update(overrides)
    return LunarContaminationEstimate(**values)


def test_contract_is_minimal_immutable_and_preserves_profile_identity():
    estimate = _estimate(filter_profile_id=" profile-id ")

    assert tuple(field.name for field in fields(estimate)) == (
        "filter_profile_id",
        "lunar_source_factor",
        "rayleigh_relative_index",
        "mie_relative_index",
    )
    assert estimate.filter_profile_id == " profile-id "
    with pytest.raises((FrozenInstanceError, AttributeError)):
        estimate.lunar_source_factor = 1.0


@pytest.mark.parametrize("profile_id", [None, 42, "", "   "])
def test_rejects_non_string_or_empty_profile_id(profile_id):
    with pytest.raises((TypeError, ValueError), match="filter_profile_id"):
        _estimate(filter_profile_id=profile_id)


@pytest.mark.parametrize(
    "field_name",
    ["lunar_source_factor", "rayleigh_relative_index", "mie_relative_index"],
)
@pytest.mark.parametrize(
    "value",
    [True, False, None, "1", float("nan"), float("inf"), -0.01],
)
def test_rejects_invalid_numeric_values(field_name, value):
    with pytest.raises((TypeError, ValueError), match=field_name):
        _estimate(**{field_name: value})


@pytest.mark.parametrize("value", [0, 0.0, 1, 1.5])
def test_accepts_finite_non_negative_numeric_values(value):
    assert _estimate(rayleigh_relative_index=value).rayleigh_relative_index == value
