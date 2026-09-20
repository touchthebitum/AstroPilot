"""Pure Pareto comparison of existing lunar-contamination estimates."""

from math import isclose

from decision.models.lunar_contamination_comparison import (
    LunarContaminationComparison,
    LunarContaminationComparisonStatus,
)
from decision.models.lunar_contamination_estimate import (
    LunarContaminationEstimate,
)


# Fixed tolerances make comparisons deterministic.  The small absolute tolerance
# handles values near zero; the relative tolerance scales floating-point noise for
# larger indices without introducing a physical weighting between components.
LUNAR_CONTAMINATION_REL_TOL = 1e-9
LUNAR_CONTAMINATION_ABS_TOL = 1e-12


def _compare_component(left: float, right: float) -> int:
    if isclose(
        left,
        right,
        rel_tol=LUNAR_CONTAMINATION_REL_TOL,
        abs_tol=LUNAR_CONTAMINATION_ABS_TOL,
    ):
        return 0
    return -1 if left < right else 1


def compare_lunar_contamination(
    left: LunarContaminationEstimate,
    right: LunarContaminationEstimate,
) -> LunarContaminationComparison:
    """Compare LEFT with RIGHT using Pareto dominance on Rayleigh and Mie."""

    if not isinstance(left, LunarContaminationEstimate):
        raise TypeError("left must be a LunarContaminationEstimate")
    if not isinstance(right, LunarContaminationEstimate):
        raise TypeError("right must be a LunarContaminationEstimate")

    rayleigh_order = _compare_component(
        left.rayleigh_relative_index,
        right.rayleigh_relative_index,
    )
    mie_order = _compare_component(
        left.mie_relative_index,
        right.mie_relative_index,
    )

    if rayleigh_order == 0 and mie_order == 0:
        status = LunarContaminationComparisonStatus.EQUIVALENT
    elif rayleigh_order <= 0 and mie_order <= 0:
        status = LunarContaminationComparisonStatus.DOMINATES
    elif rayleigh_order >= 0 and mie_order >= 0:
        status = LunarContaminationComparisonStatus.DOMINATED
    else:
        status = LunarContaminationComparisonStatus.INCOMPARABLE

    return LunarContaminationComparison(
        left_filter_profile_id=left.filter_profile_id,
        right_filter_profile_id=right.filter_profile_id,
        status=status,
    )
