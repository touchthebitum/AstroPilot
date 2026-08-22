from datetime import datetime
from zoneinfo import ZoneInfo

from decision.intelligence.analysis_context import AnalysisContext
from decision.intelligence.season_analysis import SeasonAnalysis


def test_season_analysis_uses_dynamic_season_data():
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

    result = SeasonAnalysis.analyze(context)

    assert result.analysis_name == "SeasonAnalysis"
    assert isinstance(result.data, dict)
    assert result.data["remaining_days"] is not None
    assert result.data["remaining_good_nights"] is not None
    assert result.data["end_date"] is not None
    assert result.data["peak_date"] is not None


def test_season_analysis_reports_unknown_without_dynamic_context():
    context = AnalysisContext(
        target="IC1396",
    )

    result = SeasonAnalysis.analyze(context)

    assert result.analysis_name == "SeasonAnalysis"
    assert isinstance(result.data, dict)
    assert "urgency" in result.data
    assert "remaining_days" in result.data
    assert result.data["urgency"] == "UNKNOWN"
    assert result.data["remaining_days"] is None