from types import SimpleNamespace

import astro_score


def test_unknown_duration_skips_roi_and_closure_scoring_and_reasons(monkeypatch):
    contributions = {}

    def unexpected(*args, **kwargs):
        raise AssertionError("duration-dependent scoring must be skipped")

    original_strategy_scores = (
        astro_score.night_strategy_engine.compute_strategy_scores
    )

    def record_strategy_scores(**kwargs):
        contributions.update(kwargs)
        return original_strategy_scores(**kwargs)

    monkeypatch.setattr(astro_score, "session_roi", unexpected)
    monkeypatch.setattr(astro_score, "closure_bonus", unexpected)
    monkeypatch.setattr(
        astro_score.night_strategy_engine,
        "compute_strategy_scores",
        record_strategy_scores,
    )
    monkeypatch.setattr(
        astro_score.future_engine,
        "estimate",
        lambda *args, **kwargs: SimpleNamespace(
            risk="FAIBLE",
            opportunity_ratio=1.0,
        ),
    )

    candidates = astro_score.recommend_project_for_night(
        [{"name": "M31", "catalog_key": "M31", "global_score": 80}],
        profile={
            "projects": {
                "M31": {
                    "hours": 2,
                    "target_hours": 10,
                    "importance": 5,
                }
            }
        },
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.closure_bonus == 0
    assert contributions["roi_bonus"] == 0
    assert contributions["closure_bonus"] == 0
    assert all("Rendement projet" not in reason for reason in candidate.reasons)
    assert all("finalisation" not in reason for reason in candidate.reasons)


def test_known_duration_keeps_roi_and_closure_scoring_and_reasons(monkeypatch):
    contributions = {}
    original_strategy_scores = (
        astro_score.night_strategy_engine.compute_strategy_scores
    )

    def record_strategy_scores(**kwargs):
        contributions.update(kwargs)
        return original_strategy_scores(**kwargs)

    monkeypatch.setattr(astro_score, "session_roi", lambda *args, **kwargs: 10)
    monkeypatch.setattr(astro_score, "closure_bonus", lambda *args, **kwargs: 15)
    monkeypatch.setattr(
        astro_score.night_strategy_engine,
        "compute_strategy_scores",
        record_strategy_scores,
    )
    monkeypatch.setattr(
        astro_score.future_engine,
        "estimate",
        lambda *args, **kwargs: SimpleNamespace(
            risk="FAIBLE",
            opportunity_ratio=1.0,
        ),
    )

    candidate = astro_score.recommend_project_for_night(
        [{"name": "M31", "catalog_key": "M31", "global_score": 80}],
        available_hours=3,
        profile={
            "projects": {
                "M31": {
                    "hours": 2,
                    "target_hours": 10,
                    "importance": 5,
                }
            }
        },
    )[0]

    assert contributions["roi_bonus"] == 2
    assert contributions["closure_bonus"] == 15
    assert "Rendement projet élevé pour cette session." in candidate.reasons
    assert (
        "Cette nuit rapproche nettement le projet de sa finalisation."
        in candidate.reasons
    )
