import ast
from pathlib import Path

import pytest

from decision.models.lunar_contamination_comparison import (
    LunarContaminationComparisonStatus as Status,
)
from decision.models.lunar_contamination_estimate import (
    LunarContaminationEstimate,
)
from decision.services.lunar_contamination_comparison import (
    LUNAR_CONTAMINATION_ABS_TOL,
    LUNAR_CONTAMINATION_REL_TOL,
    compare_lunar_contamination,
)


def _estimate(
    profile_id: str,
    rayleigh: float,
    mie: float,
    *,
    lunar_source_factor: float = 0.5,
) -> LunarContaminationEstimate:
    return LunarContaminationEstimate(
        filter_profile_id=profile_id,
        lunar_source_factor=lunar_source_factor,
        rayleigh_relative_index=rayleigh,
        mie_relative_index=mie,
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (_estimate("same", 2.0, 3.0), _estimate("same", 2.0, 3.0)),
        (_estimate("left", 2.0, 3.0), _estimate("right", 2.0, 3.0)),
        (_estimate("left", 0.0, 0.0), _estimate("right", 0.0, 0.0)),
    ],
)
def test_exact_equality_is_equivalent_regardless_of_profile_identity(left, right):
    result = compare_lunar_contamination(left, right)

    assert result.status is Status.EQUIVALENT
    assert result.left_filter_profile_id == left.filter_profile_id
    assert result.right_filter_profile_id == right.filter_profile_id


def test_near_equality_inside_fixed_tolerances_is_equivalent():
    left = _estimate("left", 10.0, 1e-6)
    right = _estimate(
        "right",
        10.0 + LUNAR_CONTAMINATION_REL_TOL * 5.0,
        1e-6 + LUNAR_CONTAMINATION_ABS_TOL * 0.5,
    )

    assert compare_lunar_contamination(left, right).status is Status.EQUIVALENT


@pytest.mark.parametrize(
    ("left_values", "right_values", "expected"),
    [
        ((1.0, 2.0), (2.0, 3.0), Status.DOMINATES),
        ((2.0, 3.0), (1.0, 2.0), Status.DOMINATED),
        ((1.0, 3.0), (2.0, 2.0), Status.INCOMPARABLE),
        ((3.0, 1.0), (2.0, 2.0), Status.INCOMPARABLE),
        ((1.0, 2.0), (1.0, 3.0), Status.DOMINATES),
        ((1.0, 3.0), (1.0, 2.0), Status.DOMINATED),
        ((1.0, 2.0), (2.0, 2.0), Status.DOMINATES),
        ((2.0, 2.0), (1.0, 2.0), Status.DOMINATED),
    ],
)
def test_pareto_status_uses_both_components_separately(
    left_values,
    right_values,
    expected,
):
    left = _estimate("left", *left_values)
    right = _estimate("right", *right_values)

    assert compare_lunar_contamination(left, right).status is expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (_estimate("a", 1.0, 2.0), _estimate("b", 2.0, 3.0)),
        (_estimate("a", 1.0, 3.0), _estimate("b", 2.0, 2.0)),
        (_estimate("a", 2.0, 2.0), _estimate("b", 2.0, 2.0)),
    ],
)
def test_reversing_operands_produces_the_coherent_inverse(left, right):
    inverse = {
        Status.DOMINATES: Status.DOMINATED,
        Status.DOMINATED: Status.DOMINATES,
        Status.EQUIVALENT: Status.EQUIVALENT,
        Status.INCOMPARABLE: Status.INCOMPARABLE,
    }

    forward = compare_lunar_contamination(left, right)
    reverse = compare_lunar_contamination(right, left)

    assert reverse.status is inverse[forward.status]
    assert reverse.left_filter_profile_id == forward.right_filter_profile_id
    assert reverse.right_filter_profile_id == forward.left_filter_profile_id


@pytest.mark.parametrize(
    ("left", "right", "message"),
    [
        (None, _estimate("right", 1.0, 1.0), "left"),
        (object(), _estimate("right", 1.0, 1.0), "left"),
        (_estimate("left", 1.0, 1.0), None, "right"),
        (_estimate("left", 1.0, 1.0), object(), "right"),
    ],
)
def test_rejects_wrong_input_types(left, right, message):
    with pytest.raises(TypeError, match=message):
        compare_lunar_contamination(left, right)


def test_baader_ha_and_oiii_comparison_uses_prebuilt_estimates_only():
    ha = _estimate("baader_ha_highspeed_6_5nm", 2.1, 3.8)
    oiii = _estimate("baader_oiii_highspeed_6_5nm", 5.8, 4.9)

    result = compare_lunar_contamination(ha, oiii)

    assert result.status is Status.DOMINATES
    assert result.left_filter_profile_id == "baader_ha_highspeed_6_5nm"
    assert result.right_filter_profile_id == "baader_oiii_highspeed_6_5nm"


def test_lunar_source_factor_is_not_part_of_the_relation():
    left = _estimate("left", 2.0, 3.0, lunar_source_factor=0.1)
    right = _estimate("right", 2.0, 3.0, lunar_source_factor=0.9)

    assert compare_lunar_contamination(left, right).status is Status.EQUIVALENT


def test_service_has_only_the_allowed_domain_dependency():
    source_path = (
        Path(__file__).parents[2]
        / "decision"
        / "services"
        / "lunar_contamination_comparison.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {
        "math",
        "decision.models.lunar_contamination_comparison",
        "decision.models.lunar_contamination_estimate",
    }


def test_service_defines_no_combined_score_weighting_or_absolute_status():
    source_path = (
        Path(__file__).parents[2]
        / "decision"
        / "services"
        / "lunar_contamination_comparison.py"
    )
    source = source_path.read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "lunarcontaminationestimator",
        "intentnightevidence",
        "filteropticalprofileresolver",
        "ranking",
        "preference",
        "combined_score",
        "rayleigh_weight",
        "mie_weight",
        "favorable",
        "unfavorable",
    )
    assert all(term not in source for term in forbidden_terms)
