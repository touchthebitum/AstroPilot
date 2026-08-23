from decision.risk.project_completion_estimator import (
    ProjectCompletionEstimator,
)


def test_required_nights_uses_four_productive_hours_by_default():
    assert ProjectCompletionEstimator.required_nights(15) == 4


def test_required_nights_accepts_an_explicit_nightly_capacity():
    assert ProjectCompletionEstimator.required_nights(
        remaining_hours=15,
        productive_hours_per_night=5,
    ) == 3
