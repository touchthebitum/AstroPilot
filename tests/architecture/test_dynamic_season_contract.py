from datetime import datetime
from zoneinfo import ZoneInfo

from astropilot.catalog import CATALOG
from decision.intelligence.analysis_context import AnalysisContext
from decision.season.dynamic_season_engine import (
    DynamicSeasonEngine,
    SeasonWindow,
)


def test_dynamic_season_summary_returns_typed_window():
    context = AnalysisContext(
        target="IC1396",
        latitude=46.7508,
        longitude=6.5495,
        observation_time=datetime(
            2026,
            8,
            21,
            23,
            0,
            tzinfo=ZoneInfo("Europe/Zurich"),
        ),
    )

    result = DynamicSeasonEngine.summary(
        context,
        horizon_days=30,
        min_altitude=30,
    )

    assert isinstance(result, SeasonWindow)

    assert result.start_date is not None
    assert result.end_date is not None
    assert result.peak_date is not None

    assert result.remaining_days is not None
    assert result.remaining_days >= 0

    assert result.remaining_good_nights is not None
    assert result.remaining_good_nights > 0

    assert result.urgency in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "UNKNOWN",
    }

    assert 0.0 <= result.confidence <= 1.0

def test_dynamic_season_summary_works_for_target_without_static_window():
    target_key = "M42"

    assert target_key in CATALOG

    context = AnalysisContext(
        target=target_key,
        latitude=46.7508,
        longitude=6.5495,
        observation_time=datetime(
            2026,
            10,
            15,
            23,
            0,
            tzinfo=ZoneInfo("Europe/Zurich"),
        ),
    )

    result = DynamicSeasonEngine.summary(
        context,
        horizon_days=60,
        min_altitude=30,
    )

    assert isinstance(result, SeasonWindow)
    assert result.remaining_good_nights is not None


def test_dynamic_season_requires_minimum_useful_duration():
    context = AnalysisContext(
        target="IC1396",
        latitude=46.7508,
        longitude=6.5495,
        observation_time=datetime(
            2026,
            8,
            22,
            23,
            0,
            tzinfo=ZoneInfo("Europe/Zurich"),
        ),
    )

    result = DynamicSeasonEngine.summary(
        context,
        horizon_days=180,
        min_altitude=30,
        min_useful_hours=2.0,
    )

    assert result.end_date is not None
    assert result.end_date < datetime(
        2027,
        2,
        18,
        tzinfo=ZoneInfo("Europe/Zurich"),
    ).date()


def test_rosette_season_starts_when_useful_window_reaches_two_hours():
    context = AnalysisContext(
        target="Rosette",
        latitude=46.7508,
        longitude=6.5495,
        observation_time=datetime(
            2026,
            8,
            22,
            23,
            0,
            tzinfo=ZoneInfo("Europe/Zurich"),
        ),
    )

    result = DynamicSeasonEngine.summary(
        context,
        horizon_days=180,
        min_altitude=30,
        min_useful_hours=2.0,
    )

    assert result.start_date is not None
    assert result.start_date.month == 10


def test_peak_date_prefers_longest_useful_night():
    context = AnalysisContext(
        target="IC1396",
        latitude=46.7508,
        longitude=6.5495,
        observation_time=datetime(
            2026,
            8,
            22,
            23,
            0,
            tzinfo=ZoneInfo("Europe/Zurich"),
        ),
    )

    result = DynamicSeasonEngine.summary(
        context,
        horizon_days=120,
        min_altitude=30,
        min_useful_hours=2.0,
    )

    assert result.peak_date is not None

    # Le pic ne doit plus être choisi simplement
    # par quelques centièmes de degré d'altitude maximale.
    assert result.peak_date > datetime(
        2026,
        8,
        31,
        tzinfo=ZoneInfo("Europe/Zurich"),
    ).date()
