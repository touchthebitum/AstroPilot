from decision.season.season_engine import SeasonEngine


def test_season_urgency_score_matches_summary_levels(monkeypatch):
    monkeypatch.setattr(
        SeasonEngine,
        "remaining_days",
        lambda target: 75,
    )
    assert SeasonEngine.urgency_score("IC1396") == 0

    monkeypatch.setattr(
        SeasonEngine,
        "remaining_days",
        lambda target: 30,
    )
    assert SeasonEngine.urgency_score("IC1396") == 60

    monkeypatch.setattr(
        SeasonEngine,
        "remaining_days",
        lambda target: 10,
    )
    assert SeasonEngine.urgency_score("IC1396") == 100
