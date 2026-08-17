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