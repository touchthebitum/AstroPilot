from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo

from decision.forecast.forecast_engine import ForecastEngine
import decision.forecast.forecast_engine as forecast_module


def _engine(**overrides):
    dependencies = {
        "fetch_weather": lambda lat, lon: {"source": "fetched"},
        "parse_hourly_weather": lambda weather: weather["rows"],
        "evaluate_object": lambda **kwargs: None,
        "target_objects": [],
        "moon_phase": lambda date: 0,
        "night_hours_rough": lambda *args: [],
        "timezone": "Europe/Zurich",
        "decision_engine_factory": lambda: object(),
        "altitude_rule_factory": lambda: object(),
    }
    dependencies.update(overrides)
    return ForecastEngine(**dependencies)


def test_prepare_weather_uses_explicit_payload_without_fetching():
    calls = []
    rows = [{"time": "22:00"}]
    engine = _engine(
        fetch_weather=lambda lat, lon: calls.append((lat, lon)),
        parse_hourly_weather=lambda weather: weather["rows"],
    )

    result = engine.prepare_weather(
        46.5,
        6.6,
        weather={"rows": rows},
    )

    assert result is rows
    assert calls == []


def test_prepare_weather_fetches_when_payload_is_missing():
    calls = []
    payload = {"rows": [{"time": "23:00"}]}
    engine = _engine(
        fetch_weather=lambda lat, lon: calls.append((lat, lon)) or payload,
        parse_hourly_weather=lambda weather: weather["rows"],
    )

    result = engine.prepare_weather(46.5, 6.6)

    assert result == payload["rows"]
    assert calls == [(46.5, 6.6)]


def test_prepare_weather_returns_none_when_fetch_fails(capsys):
    def fail_fetch(lat, lon):
        raise RuntimeError("weather unavailable")

    engine = _engine(fetch_weather=fail_fetch)

    assert engine.prepare_weather(46.5, 6.6) is None
    assert "prévisions météo indisponibles" in capsys.readouterr().out


def test_build_weather_forecast_preserves_rows_and_applies_defaults():
    rows = [
        {
            "cloud_cover": 12,
            "relative_humidity_2m": 65,
            "wind_speed_10m": 8,
            "temperature_2m": 4,
            "visibility": 15000,
        },
        {},
    ]

    forecast = _engine().build_weather_forecast(rows)

    assert forecast.hourly is rows
    assert forecast.hourly_clouds == [12, 100]
    assert forecast.hourly_humidity == [65, 100]
    assert forecast.hourly_wind == [8, 0]
    assert forecast.hourly_temperature == [4, 0]
    assert forecast.hourly_visibility == [15000, 10000]


def test_forecast_uses_the_weather_rows_timezone_for_lunar_calculations(
    monkeypatch,
):
    captured = []

    class Sky:
        @staticmethod
        def moon_illumination_from_phase(value):
            return 0

        @staticmethod
        def safe_moonrise(observer, date, timezone):
            captured.append(("rise", timezone.key))

        @staticmethod
        def safe_moonset(observer, date, timezone):
            captured.append(("set", timezone.key))

    monkeypatch.setattr(forecast_module, "SkyEngine", Sky)
    engine = _engine(
        night_hours_rough=lambda *args: [],
    )

    result = engine.forecast_one_night(
        night_date=datetime(2026, 9, 1).date(),
        rows=[{"time": datetime(2026, 9, 1, 22, tzinfo=ZoneInfo("Asia/Tokyo"))}],
        lat=35.6762,
        lon=139.6503,
        city="Tokyo",
        bortle=8,
        target="deep_sky",
        profile={},
    )

    assert result is None
    assert captured == [("rise", "Asia/Tokyo"), ("set", "Asia/Tokyo")]


def test_evaluate_targets_preserves_catalog_order_and_skips_none():
    calls = []

    def evaluate_object(**kwargs):
        calls.append(kwargs)
        if kwargs["obj_name"] == "M42":
            return None
        return {
            "name": kwargs["obj_name"],
            "target_altitude": None,
        }

    engine = _engine(
        evaluate_object=evaluate_object,
        target_objects=["M31", "M42", "M51"],
    )
    decision_engine = SimpleNamespace(evaluate=lambda *args: None)
    shared = {
        "sky": object(),
        "hours": [22, 23],
        "weather": object(),
        "illumination": 30,
        "moon_rise": object(),
        "moon_set": object(),
        "city_info": object(),
        "lat": 46.5,
        "lon": 6.6,
        "bortle": 4,
        "target": "M31",
        "profile": object(),
        "decision_engine": decision_engine,
    }

    results = engine.evaluate_targets(**shared)

    assert [result["name"] for result in results] == ["M31", "M51"]
    assert [call["obj_name"] for call in calls] == ["M31", "M42", "M51"]
    assert all("decision_engine" not in call for call in calls)


def test_evaluate_targets_runs_altitude_rule_only_when_altitude_exists():
    rule_calls = []
    profile = object()
    results = {
        "M31": {"name": "M31", "target_altitude": 48.0},
        "M42": {"name": "M42", "target_altitude": None},
    }
    engine = _engine(
        evaluate_object=lambda **kwargs: results[kwargs["obj_name"]],
        target_objects=["M31", "M42"],
    )
    decision_engine = SimpleNamespace(
        evaluate=lambda values, received_profile: rule_calls.append(
            (values, received_profile)
        ),
    )

    engine.evaluate_targets(
        sky=object(),
        hours=[],
        weather=object(),
        illumination=0,
        moon_rise=None,
        moon_set=None,
        city_info=object(),
        lat=0,
        lon=0,
        bortle=1,
        target="M31",
        profile=profile,
        decision_engine=decision_engine,
    )

    assert rule_calls == [({"altitude": 48.0}, profile)]


def test_evaluate_night_returns_none_without_candidates():
    assert _engine().evaluate_night(all_results=[]) is None


def test_evaluate_night_ranks_top_three_and_averages_their_scores():
    results = [
        {"name": "M42", "global_score": 70, "window": "w42"},
        {
            "name": "M31",
            "global_score": 95,
            "window": "w31",
            "best_setup": "widefield",
        },
        {"name": "M51", "global_score": 80, "window": "w51"},
        {"name": "M81", "global_score": 60, "window": "w81"},
    ]

    evaluation = _engine().evaluate_night(all_results=results)

    assert [result["name"] for result in evaluation.all_results] == [
        "M31",
        "M51",
        "M42",
        "M81",
    ]
    assert [result["name"] for result in evaluation.top3] == [
        "M31",
        "M51",
        "M42",
    ]
    assert evaluation.best_score == 95
    assert evaluation.best_object == "M31"
    assert evaluation.best == "w31"
    assert evaluation.setup_name == "widefield"
    assert evaluation.night_score == 82


def test_evaluate_night_uses_unknown_setup_and_fresh_top_object_lists():
    first = _engine().evaluate_night(
        all_results=[{"name": "M31", "global_score": 80, "window": {}}],
    )
    second = _engine().evaluate_night(
        all_results=[{"name": "M42", "global_score": 70, "window": {}}],
    )

    first.top_objects_for_night.append("M31")

    assert first.setup_name == "inconnu"
    assert second.top_objects_for_night == []
