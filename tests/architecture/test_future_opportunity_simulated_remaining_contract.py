from decision.engines.future_opportunity_engine import (
    FutureOpportunityEngine,
)


def test_estimate_can_use_simulated_remaining_hours():
    engine = FutureOpportunityEngine(
        catalog={
            "M31": {
                "name": "M31",
            }
        },
        weather_provider=lambda lat, lon: None,
        season_engine=lambda project: 30,
        profile_provider=lambda: {
            "location": {
                "latitude": None,
                "longitude": None,
            }
        },
        project_provider=lambda name: 18,
    )

    real = engine.estimate("M31")

    simulated = engine.estimate(
        "M31",
        remaining_hours=6,
    )

    assert real.needed_nights == 6
    assert simulated.needed_nights == 2
    assert (
        simulated.opportunity_ratio
        > real.opportunity_ratio
    )

def test_weather_good_night_ratio_ignores_daytime_hours():
    weather = {
        "hourly": {
            "time": [
                "2026-08-22T02:00",
                "2026-08-22T12:00",
                "2026-08-22T23:00",
            ],
            "cloud_cover": [0, 100, 0],
            "relative_humidity_2m": [50, 100, 50],
            "wind_speed_10m": [5, 99, 5],
            "precipitation": [0, 10, 0],
        }
    }

    ratio = (
        FutureOpportunityEngine
        ._estimate_weather_good_night_ratio(weather)
    )

    assert ratio == 1.0
