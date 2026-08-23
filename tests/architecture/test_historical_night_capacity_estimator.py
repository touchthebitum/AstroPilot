from decision.portfolio.historical_night_capacity_estimator import (
    HistoricalNightCapacityEstimator,
)


def test_capacity_averages_totals_grouped_by_night():
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
    ]

    capacity = HistoricalNightCapacityEstimator.estimate(
        sessions=sessions,
        fallback=4.0,
    )

    assert capacity == 4.0


def test_capacity_uses_fallback_without_session_history():
    capacity = HistoricalNightCapacityEstimator.estimate(
        sessions=[],
        fallback=4.5,
    )

    assert capacity == 4.5
