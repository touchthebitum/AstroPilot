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

def test_estimate_accepts_explicit_observation_context():
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

    result = engine.estimate(
        "M31",
        remaining_hours=6,
        latitude=46.7508,
        longitude=6.5495,
        observation_time=None,
    )

    assert result.needed_nights == 2

def test_estimate_uses_dynamic_season_with_observation_context(
    monkeypatch,
):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    captured = {}

    def fake_resolve(context):
        captured["target"] = context.target
        captured["latitude"] = context.latitude
        captured["longitude"] = context.longitude
        captured["observation_time"] = (
            context.observation_time
        )

        return {
            "remaining_days": 20,
            "remaining_good_nights": 10,
            "urgency": "MEDIUM",
            "source": "dynamic",
            "confidence": 0.9,
        }

    monkeypatch.setattr(
        "decision.engines.future_opportunity_engine."
        "SeasonResolver.resolve",
        fake_resolve,
    )

    engine = FutureOpportunityEngine(
        catalog={
            "M31": {
                "name": "M31",
                "ra": 10.6847,
                "dec": 41.2692,
            }
        },
        weather_provider=lambda lat, lon: None,
        season_engine=lambda project: 999,
        profile_provider=lambda: {
            "location": {
                "latitude": None,
                "longitude": None,
            }
        },
        project_provider=lambda name: 6,
    )

    observation_time = datetime(
        2026,
        8,
        27,
        23,
        0,
        tzinfo=ZoneInfo("Europe/Zurich"),
    )

    engine.estimate(
        "M31",
        latitude=46.7508,
        longitude=6.5495,
        observation_time=observation_time,
    )

    assert captured == {
        "target": "M31",
        "latitude": 46.7508,
        "longitude": 6.5495,
        "observation_time": observation_time,
    }
