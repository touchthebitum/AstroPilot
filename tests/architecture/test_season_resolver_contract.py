from datetime import datetime
from zoneinfo import ZoneInfo

from decision.intelligence.analysis_context import (
    AnalysisContext,
)
from decision.season.season_resolver import SeasonResolver


def test_season_resolver_prefers_dynamic_season():
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

    result = SeasonResolver.resolve(context)

    assert result["source"] == "dynamic"
    assert result["remaining_days"] is not None
    assert result["remaining_good_nights"] is not None
    assert result["end_date"] is not None
    assert result["peak_date"] is not None
    assert result["urgency"] in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "UNKNOWN",
    }


def test_season_resolver_falls_back_without_observation_context():
    context = AnalysisContext(
        target="IC1396",
    )

    result = SeasonResolver.resolve(context)

    assert result["source"] == "legacy"
    assert "remaining_days" in result
    assert "remaining_good_nights" in result
    assert "urgency" in result