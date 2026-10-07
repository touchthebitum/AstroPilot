from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from decision.mission.mission_assembler import ProductiveWindowAssessment
from decision.mission.mission_input import MissionInput
from decision.models.session_availability import SessionAvailability, SessionAvailabilityMode
from decision.services.session_availability_windowing import evaluate_authorized_session_window
from decision.weather.weather_forecast import WeatherForecast
from decision.night_productivity.night_productivity_context import NightProductivityContext
from decision.night_productivity.night_productivity_engine import NightProductivityEngine
from decision.night_productivity.night_conditions_provider import NightConditionsProvider

START = datetime(2026, 10, 7, 20, tzinfo=timezone.utc)
FIELDS = ('hourly_clouds', 'hourly_humidity', 'hourly_wind', 'hourly_seeing', 'hourly_moon_penalty')


def inputs(weather=True):
    forecast = WeatherForecast(
        hourly_clouds=[10., 10.], hourly_humidity=[50., 50.],
        hourly_wind=[5., 5.], hourly_seeing=[1.5, 1.5],
        hourly_moon_penalty=[.2, .2],
    ) if weather else None
    context = SimpleNamespace(
        site=SimpleNamespace(latitude=46.75, longitude=6.55),
        session=SimpleNamespace(start_time=START, end_time=START + timedelta(hours=2)),
        # Deliberately favorable competing aggregates: never repair a partial forecast.
        weather=SimpleNamespace(cloud_cover=0., humidity=20., wind_speed_kmh=0., seeing_arcsec=1.),
    )
    mission = MissionInput(START, START + timedelta(hours=2), 2., forecast, .0, 2., 10.)
    return context, mission


def assess(context, mission):
    return ProductiveWindowAssessment.build(target='M31', context=context, mission_input=mission)


def assert_closed(result):
    assert result.evidence_issues
    assert result.recommended_hours == result.expected_gain == 0
    assert result.productivity.productive_hours == result.productivity.confidence == 0
    assert result.productivity.windows == []
    selection = evaluate_authorized_session_window(result, SessionAvailability(SessionAvailabilityMode.ALL_NIGHT))
    assert selection.window is None
    assert selection.refusal.status.value == 'insufficient_evidence'


@pytest.fixture(autouse=True)
def altitude(monkeypatch):
    monkeypatch.setattr('decision.night_productivity.night_conditions_provider.DynamicSeasonEngine.target_altitude_at_time', lambda **kwargs: 60.)


@pytest.mark.parametrize('field', FIELDS)
@pytest.mark.parametrize('replacement', [None, [], [10.], [None, None], [float('nan'), 0.], [float('inf'), 0.], [True, True]])
def test_removing_or_corrupting_series_cannot_improve_decision(field, replacement):
    context, mission = inputs()
    complete = assess(context, mission)
    assert not complete.evidence_issues
    assert complete.recommended_hours > 0
    partial = assess(context, replace(mission, weather=replace(mission.weather, **{field: replacement})))
    assert_closed(partial)
    assert partial.productivity.productive_hours <= complete.productivity.productive_hours
    assert partial.expected_gain <= complete.expected_gain


@pytest.mark.parametrize('field,value', [('hourly_clouds', -1), ('hourly_clouds', 101), ('hourly_humidity',101), ('hourly_wind',-1), ('hourly_seeing',0), ('hourly_moon_penalty',1.01)])
def test_out_of_domain_series_fail_closed(field, value):
    context, mission = inputs()
    assert_closed(assess(context, replace(mission, weather=replace(mission.weather, **{field:[value, value]}))))


def test_empty_hourly_forecast_is_not_replaced_by_context():
    context, mission = inputs()
    assert_closed(assess(context, replace(mission, weather=WeatherForecast())))


@pytest.mark.parametrize('field', ['cloud_cover', 'humidity', 'wind_speed_kmh', 'seeing_arcsec'])
def test_explicit_scalar_evidence_missing_fails_closed(field):
    context, mission = inputs(weather=False)
    assert not assess(context, mission).evidence_issues
    setattr(context.weather, field, None)
    assert_closed(assess(context, mission))


def test_scalar_lunar_evidence_missing_is_not_point_two():
    context, mission = inputs(weather=False)
    assert_closed(assess(context, replace(mission, moon_penalty=None)))


def test_duration_missing_is_not_six_hours():
    context, mission = inputs(weather=False)
    context.session = None
    result = assess(context, replace(mission, window_start=None, window_end=None, astronomical_hours=None))
    assert_closed(result)
    assert result.productivity.astronomical_hours == 0


@pytest.mark.parametrize('hours', [-1, True, float('nan'), float('inf'), 3])
def test_invalid_duration_never_creates_gain(hours):
    context, mission = inputs()
    assert_closed(assess(context, replace(mission, astronomical_hours=hours)))


def test_series_cannot_repeat_last_sample():
    with pytest.raises(ValueError, match='hourly_evidence_uncovered'):
        NightConditionsProvider._value(1.25, [10.], 0.)


def test_engine_rejects_direct_incomplete_internal_context():
    context = NightProductivityContext(2., 0., 0., 8., 40., 0., 1.5, hourly_moon_penalty=[0.])
    with pytest.raises(ValueError, match='hourly_moon_penalty_incomplete'):
        NightProductivityEngine.evaluate(context)


def test_unrelated_temperature_missing_does_not_invent_or_improve_productivity():
    context, mission = inputs()
    with_temperature = assess(context, replace(mission, weather=replace(mission.weather, hourly_temperature=[5., 5.])))
    without_temperature = assess(context, mission)
    assert without_temperature.productivity == with_temperature.productivity
    assert without_temperature.expected_gain == with_temperature.expected_gain


@pytest.mark.parametrize("field", ["window_start", "window_end"])
@pytest.mark.parametrize("value", [None, "invalid", START.replace(tzinfo=None)])
def test_invalid_window_never_creates_gain(field, value):
    context, mission = inputs()
    assert_closed(assess(context, replace(mission, astronomical_hours=None, **{field: value})))


@pytest.mark.parametrize("missing", ["cloud_cover", "relative_humidity_2m", "wind_speed_10m"])
def test_forecast_builder_preserves_missing_evidence_through_assessment(missing):
    from decision.forecast.forecast_engine import ForecastEngine
    context, mission = inputs()
    row = {"cloud_cover": 10., "relative_humidity_2m": 50., "wind_speed_10m": 5.}
    del row[missing]
    forecast = ForecastEngine.build_weather_forecast(None, [row, row])
    forecast = replace(forecast, hourly_seeing=[1.5, 1.5], hourly_moon_penalty=[.2, .2])
    assert_closed(assess(context, replace(mission, weather=forecast)))


@pytest.mark.parametrize('missing', ['cloud_cover', 'relative_humidity_2m', 'wind_speed_10m'])
def test_selected_builder_never_estimates_from_invented_weather(missing):
    import astro_score
    context, mission = inputs()
    rows = [{"time": START + timedelta(hours=i), "cloud_cover": 10.,
             "relative_humidity_2m": 50., "wind_speed_10m": 5.} for i in range(2)]
    for row in rows:
        del row[missing]
    calls = []
    forecast = astro_score.build_selected_window_weather(
        hours=rows,
        best={"start": START, "end": START + timedelta(hours=2),
              "details": [{"moon": .2}, {"moon": .2}]},
        sky=SimpleNamespace(estimate_seeing=lambda *values: calls.append(values) or 1.5),
    )
    assert_closed(assess(context, replace(mission, weather=forecast)))
    if missing in ('relative_humidity_2m', 'wind_speed_10m'):
        assert calls == []
        assert forecast.hourly_seeing == [None, None]


@pytest.mark.parametrize("field", FIELDS)
def test_engine_cannot_repair_partial_forecast_with_scalar_context(field):
    _, mission = inputs()
    context = NightProductivityContext(2., 0., 0., 8., 40., 0., 1.5,
        weather=replace(mission.weather, **{field: None}))
    with pytest.raises(ValueError, match=field + "_missing"):
        NightProductivityEngine.evaluate(context)
