from datetime import datetime
from zoneinfo import ZoneInfo

import astro_score


def test_night_capacity_preserves_observation_context():
    timestamp = datetime(
        2026,
        8,
        22,
        23,
        0,
        tzinfo=ZoneInfo("Europe/Zurich"),
    )

    weather = {
        "hourly": {
            "time": [
                timestamp.isoformat(),
            ],
            "cloud_cover": [0],
            "cloud_cover_low": [0],
            "cloud_cover_mid": [0],
            "cloud_cover_high": [0],
            "precipitation": [0],
            "relative_humidity_2m": [50],
            "visibility": [10000],
            "wind_speed_10m": [5],
            "temperature_2m": [10],
        }
    }

    capacities = astro_score.forecast_night_capacities(
        46.7508,
        6.5495,
        weather=weather,
    )

    assert len(capacities) == 1

    capacity = capacities[0]

    assert capacity["date"] == "2026-08-22"
    assert capacity["latitude"] == 46.7508
    assert capacity["longitude"] == 6.5495

    assert capacity["observation_time"].date().isoformat() == (
        "2026-08-22"
    )
    assert capacity["observation_time"].hour == 23
    assert capacity["observation_time"].tzinfo is not None