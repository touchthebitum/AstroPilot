from datetime import datetime

import astropilot.engines.sky_engine as sky_engine_module
from astropilot.engines.sky_engine import SkyEngine


def test_sky_windows_use_long_altitude_preference_alias(monkeypatch):
    engine = SkyEngine()
    hour = {"time": datetime(2026, 8, 28, 22)}

    monkeypatch.setattr(
        sky_engine_module,
        "load_user_profile",
        lambda: {"preferences": {"minimum_altitude_deg": 35}},
    )
    monkeypatch.setattr(engine, "iter_windows", lambda hours, size: [[hour]])
    monkeypatch.setattr(
        engine,
        "moon_visible_during_window",
        lambda *args: False,
    )
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
        moon_rise=None,
        moon_set=None,
        observer=object(),
        lat=46.75,
        lon=6.55,
        target_obj={},
        window_size=1,
    ) == []
