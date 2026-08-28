from datetime import datetime
from types import SimpleNamespace

import astro_score
from astropilot.engines.sky_engine import SkyEngine


def test_window_preferences_are_passed_to_sky_engine():
    observed = {}

    class CapturingSky:
        def best_windows(self, **kwargs):
            observed.update(kwargs)
            return []

    assert astro_score.compute_best_window_for_object(
        sky=CapturingSky(),
        hours=[],
        illumination=0,
        city_info=SimpleNamespace(observer=object()),
        lat=46.75,
        lon=6.55,
        bortle=4,
        target="deep_sky",
        obj_name="M31",
        profile={
            "preferences": {
                "window_size": 3,
                "minimum_altitude_deg": 35,
            },
        },
    ) is None
    assert observed["window_size"] == 3
    assert observed["min_altitude_deg"] == 35


def test_sky_windows_use_explicit_minimum_altitude(monkeypatch):
    engine = SkyEngine()
    hour = {"time": datetime(2026, 8, 28, 22)}

    monkeypatch.setattr(engine, "iter_windows", lambda hours, size: [[hour]])
    monkeypatch.setattr(
        engine,
        "hour_geometry",
        lambda *args: {
            "moon_elevation": -10,
            "target_altitude": 32,
            "moon_target_sep": 180,
        },
    )

    def fail_if_scored(*args, **kwargs):
        raise AssertionError("hour below configured altitude was scored")

    monkeypatch.setattr(engine, "score_hour", fail_if_scored)

    assert engine.best_windows(
        [hour],
        moon_illumination=0,
        observer=object(),
        lat=46.75,
        lon=6.55,
        target_obj={},
        window_size=1,
        min_altitude_deg=35,
    ) == []
