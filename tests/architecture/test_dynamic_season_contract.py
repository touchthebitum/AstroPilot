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