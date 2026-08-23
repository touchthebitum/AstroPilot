from decision.portfolio.historical_night_capacity_estimator import (
    HistoricalNightCapacityEstimator,
)


def test_capacity_averages_totals_after_three_nights():
    sessions = [
        {
            "date": "2026-08-16",
            "object": "M31",
            "hours": 2.0,
        },
        {
            "date": "2026-08-16",
            "object": "Rosette",
            "hours": 1.0,
        },
        {
            "date": "2026-08-17",
            "object": "IC1396",
            "hours": 5.0,
        },
        {
            "date": "2026-08-18",
            "object": "M31",
            "hours": 4.0,
        },
    ]

    estimate = HistoricalNightCapacityEstimator.estimate(
        sessions=sessions,
        fallback=6.0,
    )

    assert estimate.productive_hours_per_night == 4.0
    assert estimate.source == "history"
    assert estimate.historical_nights == 3


def test_capacity_uses_fallback_with_fewer_than_three_nights():
    sessions = [
        {
            "date": "2026-08-16",
            "object": "M31",
            "hours": 3.0,
        },
        {
            "date": "2026-08-17",
            "object": "IC1396",
            "hours": 5.0,
        },
    ]

    estimate = HistoricalNightCapacityEstimator.estimate(
        sessions=sessions,
        fallback=6.0,
    )

    assert estimate.productive_hours_per_night == 6.0
    assert estimate.source == "profile"
    assert estimate.historical_nights == 2


def test_capacity_uses_fallback_without_session_history():
    estimate = HistoricalNightCapacityEstimator.estimate(
        sessions=[],
        fallback=4.5,
    )

    assert estimate.productive_hours_per_night == 4.5
    assert estimate.source == "profile"
    assert estimate.historical_nights == 0
