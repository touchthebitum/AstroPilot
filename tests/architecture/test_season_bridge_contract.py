import astro_score


def test_legacy_season_days_remaining_delegates_to_season_engine(
    monkeypatch,
):
    monkeypatch.setattr(
        astro_score.SeasonEngine,
        "season_days_remaining",
        lambda obj: 42,
    )

    assert astro_score.season_days_remaining(
        {"name": "M31"}
    ) == 42

def test_legacy_season_urgency_bonus_delegates_to_season_engine(
    monkeypatch,
):
    monkeypatch.setattr(
        astro_score.SeasonEngine,
        "urgency_bonus",
        lambda obj: 15,
    )

    assert astro_score.season_urgency_bonus(
        {"name": "M31"}
    ) == 15

def test_season_engine_urgency_bonus_preserves_legacy_thresholds(
    monkeypatch,
):
    monkeypatch.setattr(
        astro_score.SeasonEngine,
        "remaining_days",
        lambda target: 45,
    )

    assert astro_score.SeasonEngine.urgency_bonus("M31") == 15