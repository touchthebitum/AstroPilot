import pytest

from decision.night_productivity.night_timeline_builder import (
    NightTimelineBuilder,
)


def test_perfect_conditions_produce_full_productivity():
    result = NightTimelineBuilder._compute_productivity(
        cloud_cover=0.0,
        moon_penalty=0.0,
        target_altitude=60.0,
        humidity=50.0,
        wind=5.0,
    )

    assert result == pytest.approx(1.0)


def test_cloud_and_moon_penalties_are_combined():
    result = NightTimelineBuilder._compute_productivity(
        cloud_cover=50.0,
        moon_penalty=0.5,
        target_altitude=60.0,
        humidity=50.0,
        wind=5.0,
    )

    assert result == pytest.approx(0.55)


def test_environmental_penalties_are_cumulative():
    result = NightTimelineBuilder._compute_productivity(
        cloud_cover=0.0,
        moon_penalty=0.0,
        target_altitude=20.0,
        humidity=90.0,
        wind=25.0,
    )

    assert result == pytest.approx(0.45)


def test_productivity_is_clamped_at_zero():
    result = NightTimelineBuilder._compute_productivity(
        cloud_cover=100.0,
        moon_penalty=1.0,
        target_altitude=20.0,
        humidity=90.0,
        wind=25.0,
    )

    assert result == 0.0


from datetime import datetime

from decision.night_productivity.night_productivity_context import (
    NightProductivityContext,
)
from decision.night_productivity.night_productivity_engine import (
    NightProductivityEngine,
)


def test_productive_hours_are_derived_from_timeline_slices(
    monkeypatch,
):
    monkeypatch.setattr(
        "decision.night_productivity.night_conditions_provider."
        "DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: 60.0,
    )

    context = NightProductivityContext(
        astronomical_hours=1.0,
        cloud_cover=0.0,
        moon_penalty=0.0,
        altitude_score=8,
        humidity=50.0,
        wind=5.0,
        seeing=1.5,
        weather=None,
        hourly_seeing=None,
        hourly_moon_penalty=None,
        target={"ra": 10.0, "dec": 20.0},
        latitude=46.7508,
        longitude=6.5495,
        observation_time=datetime(2026, 8, 26, 22, 0),
    )

    result = NightProductivityEngine.evaluate(context)

    assert len(result.timeline.slices) == 4

    expected = sum(
        (night_slice.end_hour - night_slice.start_hour)
        * night_slice.productivity_score
        for night_slice in result.timeline.slices
    )

    assert result.productive_hours == pytest.approx(
        round(expected, 2)
    )


def test_productivity_confidence_is_productive_fraction(
    monkeypatch,
):
    monkeypatch.setattr(
        "decision.night_productivity.night_conditions_provider."
        "DynamicSeasonEngine.target_altitude_at_time",
        lambda **kwargs: 60.0,
    )

    context = NightProductivityContext(
        astronomical_hours=1.0,
        cloud_cover=50.0,
        moon_penalty=0.5,
        altitude_score=8,
        humidity=50.0,
        wind=5.0,
        seeing=1.5,
        weather=None,
        hourly_seeing=None,
        hourly_moon_penalty=None,
        target={"ra": 10.0, "dec": 20.0},
        latitude=46.7508,
        longitude=6.5495,
        observation_time=datetime(2026, 8, 26, 22, 0),
    )

    result = NightProductivityEngine.evaluate(context)

    assert result.confidence == pytest.approx(
        round(
            result.productive_hours
            / result.astronomical_hours,
            2,
        )
    )
