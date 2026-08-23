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

    capacity = HistoricalNightCapacityEstimator.estimate(
        sessions=sessions,
        fallback=6.0,
    )

    assert capacity == 4.0


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

    capacity = HistoricalNightCapacityEstimator.estimate(
        sessions=sessions,
        fallback=6.0,
    )

    assert capacity == 6.0


def test_capacity_uses_fallback_without_session_history():
    capacity = HistoricalNightCapacityEstimator.estimate(
        sessions=[],
        fallback=4.5,
    )

    assert capacity == 4.5

