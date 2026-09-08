from types import SimpleNamespace

import astro_score
import pytest
from decision.engines.project_selection_engine import ProjectSelectionEngine
from decision.models.candidate import CandidateProvenance
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation


def test_candidate_provenance_has_exact_values_and_defaults_to_project():
    assert {item.value for item in CandidateProvenance} == {
        "project",
        "discovery",
    }

    candidate = ProjectSelectionEngine.build_candidate(
        name="Andromeda",
        catalog_key="M31",
        priority=1,
        astro_score=80,
        final_score=70,
        decision_score=70,
        portfolio_score=14,
        global_score=80,
        setup_score=10,
        best_setup="samyang_183",
        closure_bonus=0,
        reasons=[],
        strategy_scores={},
        acquired_hours=2,
    )

    assert candidate.provenance is CandidateProvenance.PROJECT


def test_candidate_identity_and_provenance_survive_winner_wrappers():
    candidate = ProjectSelectionEngine.build_candidate(
        name="Orion",
        catalog_key="M42",
        priority=None,
        astro_score=90,
        final_score=63,
        decision_score=63,
        portfolio_score=None,
        global_score=90,
        setup_score=12,
        best_setup="samyang_183",
        closure_bonus=None,
        reasons=[],
        strategy_scores={},
        acquired_hours=None,
        provenance=CandidateProvenance.DISCOVERY,
    )

    winner = ProjectSelectionEngine.rank_candidates([candidate])[0]
    opportunity = Opportunity(action=Action.START_PROJECT, candidate=winner)
    recommendation = Recommendation(opportunity=opportunity, confidence=None)

    assert winner is candidate
    assert opportunity.candidate is candidate
    assert recommendation.opportunity.candidate is candidate
    assert candidate.provenance is CandidateProvenance.DISCOVERY


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
    assert candidate.provenance is CandidateProvenance.PROJECT
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


def test_empty_projects_builds_ranked_discovery_from_evaluated_objects(
    monkeypatch,
):
    def unexpected(*args, **kwargs):
        raise AssertionError("discovery must skip project-only calculations")

    for attribute in (
        "project_priority",
        "session_roi",
        "project_remaining_hours",
        "risk_label_to_score",
        "compute_postponement_impact",
        "project_progress",
        "marginal_gain_factor",
        "closure_bonus",
        "diversification_bonus",
        "portfolio_candidate_bonus",
        "explain_recommendation",
    ):
        monkeypatch.setattr(astro_score, attribute, unexpected)
    monkeypatch.setattr(astro_score.future_engine, "estimate", unexpected)

    candidates = astro_score.recommend_project_for_night(
        [
            {
                "name": "Orion Nebula",
                "catalog_key": "M42",
                "global_score": 90,
                "setup_score": 12,
                "best_setup": "samyang_183",
            },
            {
                "name": "Andromeda Galaxy",
                "catalog_key": "M31",
                "global_score": 70,
                "setup_score": 8,
                "best_setup": "fra400_2600",
            },
            {
                "name": "Unavailable Target",
                "catalog_key": "M1",
                "global_score": 0,
            },
        ],
        profile={"projects": {}},
    )

    assert [candidate.catalog_key for candidate in candidates] == ["M42", "M31"]
    assert candidates[0].astro_score == 90
    assert candidates[0].global_score == 90
    assert candidates[0].setup_score == 12
    assert candidates[0].best_setup == "samyang_183"
    assert candidates[0].final_score == pytest.approx(63)
    assert candidates[0].decision_score == pytest.approx(63)
    assert candidates[0].priority is None
    assert candidates[0].portfolio_score is None
    assert candidates[0].closure_bonus is None
    assert candidates[0].acquired_hours is None
    assert candidates[0].reasons == []
    assert candidates[0].strategy_scores == {}
    assert candidates[0].provenance is CandidateProvenance.DISCOVERY


def test_viable_project_candidate_suppresses_discovery(monkeypatch):
    monkeypatch.setattr(
        astro_score.future_engine,
        "estimate",
        lambda *args, **kwargs: SimpleNamespace(
            risk="FAIBLE",
            opportunity_ratio=1.0,
        ),
    )

    candidates = astro_score.recommend_project_for_night(
        [
            {"name": "Andromeda", "catalog_key": "M31", "global_score": 60},
            {"name": "Orion", "catalog_key": "M42", "global_score": 100},
        ],
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

    assert [candidate.catalog_key for candidate in candidates] == ["M31"]


def test_discovery_is_used_when_configured_project_is_not_viable(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("non-viable projects must not be scored")

    monkeypatch.setattr(astro_score.future_engine, "estimate", unexpected)

    candidates = astro_score.recommend_project_for_night(
        [
            {"name": "Andromeda", "catalog_key": "M31", "global_score": 0},
            {"name": "Orion", "catalog_key": "M42", "global_score": 80},
        ],
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

    assert [candidate.catalog_key for candidate in candidates] == ["M42"]
