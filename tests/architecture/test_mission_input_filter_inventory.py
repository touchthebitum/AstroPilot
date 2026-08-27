from datetime import timedelta

import astro_score


def test_mission_input_allows_empty_filter_inventory(
    monkeypatch,
    frozen_time,
):
    monkeypatch.setattr(
        astro_score.FilterInventoryLoader,
        "load",
        lambda: (),
    )

    mission_input = astro_score.build_mission_input(
        {
            "catalog_key": "IC1396",
            "window": {
                "start": frozen_time,
                "end": frozen_time + timedelta(hours=2),
                "moon_penalty": 0.2,
            },
            "remaining_hours": 2.0,
        }
    )

    assert mission_input.selected_filter is None
