from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import astropilot.engines.sky_engine as sky_module
from astro_score import TARGET_OBJECTS, framing_score
from astropilot.catalog import CATALOG
from astropilot.engines.sky_engine import SkyEngine
from astropilot.equipment_catalog import EQUIPMENT_PROFILES


def _target_score(monkeypatch, target_obj, *, goal="balanced"):
    engine = SkyEngine()
    hour = {
        "time": datetime(2026, 10, 15, 22, tzinfo=ZoneInfo("Europe/Zurich")),
        "relative_humidity_2m": 50.0,
        "wind_speed_10m": 5.0,
        "visibility": 20_000.0,
        "cloud_cover_low": 0.0,
        "cloud_cover_mid": 0.0,
        "cloud_cover_high": 0.0,
    }

    monkeypatch.setattr(
        engine,
        "hour_geometry",
        lambda *args: {
            "moon_elevation": -10.0,
            "target_altitude": 60.0,
            "moon_target_sep": 180.0,
        },
    )
    monkeypatch.setattr(
        engine,
        "score_hour",
        lambda *args: {
            "score": 50.0,
            "moon_impact": 0.0,
            "moon_penalty": 0.0,
            "details": {
                "target_altitude": 60.0,
                "moon_sep": 180.0,
                "sqm": 21.0,
                "frame_bonus": 0.0,
            },
        },
    )
    monkeypatch.setattr(sky_module.moon, "elevation", lambda *args: -10.0)

    windows = engine.best_windows(
        hours=[hour],
        moon_illumination=0.0,
        observer=object(),
        lat=46.75,
        lon=6.55,
        target_obj=target_obj,
        goal=goal,
        window_size=1,
    )

    assert len(windows) == 1
    return windows[0]["score"]


def test_production_targets_preserve_sky_scoring_catalog_metadata():
    required_fields = {
        "ra",
        "dec",
        "size_arcmin",
        "type",
        "magnitude",
        "difficulty",
    }

    assert required_fields <= TARGET_OBJECTS["M31"].keys()
    assert {
        field: TARGET_OBJECTS["M31"][field]
        for field in required_fields
    } == {
        field: CATALOG["M31"][field]
        for field in required_fields
    }


def test_real_catalog_type_controls_goal_preference(monkeypatch):
    galaxy_balanced = _target_score(monkeypatch, TARGET_OBJECTS["M31"])
    galaxy_goal = _target_score(
        monkeypatch,
        TARGET_OBJECTS["M31"],
        goal="galaxies",
    )
    nebula_galaxy_goal = _target_score(
        monkeypatch,
        TARGET_OBJECTS["M42"],
        goal="galaxies",
    )

    assert galaxy_goal == galaxy_balanced + 25
    assert nebula_galaxy_goal == _target_score(
        monkeypatch,
        TARGET_OBJECTS["M42"],
    )


def test_catalog_magnitude_and_difficulty_affect_target_adjustment(monkeypatch):
    assert _target_score(monkeypatch, TARGET_OBJECTS["M31"]) == 58
    assert _target_score(monkeypatch, TARGET_OBJECTS["M51"]) == 50


@pytest.mark.parametrize("size_arcmin", [5.0, 150.0])
def test_sky_scoring_has_no_setup_independent_framing_penalty(
    monkeypatch,
    size_arcmin,
):
    target = {
        "ra": 10.0,
        "dec": 20.0,
        "size_arcmin": size_arcmin,
        "type": "galaxy",
        "magnitude": 8.0,
        "difficulty": 3,
    }

    assert _target_score(monkeypatch, target) == 50


def test_real_catalog_semantics_can_change_representative_target_ranking(
    monkeypatch,
):
    scores = {
        name: _target_score(monkeypatch, TARGET_OBJECTS[name])
        for name in ("M31", "M51")
    }

    assert max(scores, key=scores.get) == "M31"
    assert scores["M31"] > scores["M51"]


def test_setup_specific_framing_remains_authoritative():
    assert framing_score(EQUIPMENT_PROFILES["samyang_183"], "M42") == 15
    assert framing_score(EQUIPMENT_PROFILES["fra400_2600"], "M42") == 25
