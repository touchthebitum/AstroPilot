from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import astro_score
import pytest
from decision.engines.project_selection_engine import ProjectSelectionEngine
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.candidate_rejection import (
    CandidateBuildResult,
    CandidateRejection,
    CandidateRejectionBasis,
)
from decision.opportunity.action import Action
from decision.opportunity.opportunity import Opportunity
from decision.recommendation.recommendation import Recommendation
from decision.services.project_imaging_field_resolution import (
    ProjectImagingFieldResolutionError,
)


def build_project_candidate(monkeypatch, project):
    monkeypatch.setattr(
        astro_score.future_engine,
        "estimate",
        lambda *args, **kwargs: SimpleNamespace(
            risk="FAIBLE",
            opportunity_ratio=1.0,
        ),
    )
    return astro_score.recommend_project_for_night(
        [
            {
                "name": "Flying Bat and Squid Nebulae",
                "catalog_key": "Sh2-129",
                "global_score": 80,
            }
        ],
        profile={"projects": {"Sh2-129": project}},
    )[0]


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


@pytest.mark.parametrize("provenance", ["project", "discovery", None])
def test_candidate_rejects_raw_or_invalid_provenance(provenance):
    with pytest.raises(ValueError, match="CandidateProvenance"):
        Candidate(
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
            provenance=provenance,
        )


def test_candidate_imaging_field_and_provenance_survive_winner_wrappers():
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
        provenance=CandidateProvenance.PROJECT,
        imaging_field_id="sh2-129_ou4",
    )

    winner = ProjectSelectionEngine.rank_candidates([candidate])[0]
    opportunity = Opportunity(
        action=Action.START_PROJECT,
        candidate=winner,
        shortlist_entries=(winner,),
    )
    recommendation = Recommendation(opportunity=opportunity, confidence=None)

    assert winner is candidate
    assert opportunity.candidate is candidate
    assert recommendation.opportunity.candidate is candidate
    assert opportunity.shortlist_entries[0].imaging_field_id == "sh2-129_ou4"
    assert recommendation.opportunity.candidate.imaging_field_id == (
        "sh2-129_ou4"
    )
    assert candidate.provenance is CandidateProvenance.PROJECT


def test_project_candidate_carries_canonical_imaging_field_id(monkeypatch):
    candidate = build_project_candidate(
        monkeypatch,
        {
            "hours": 2,
            "target_hours": 10,
            "importance": 5,
            "imaging_field_id": "sh2-129_ou4",
        },
    )

    assert candidate.imaging_field_id == "sh2-129_ou4"


def test_legacy_project_candidate_has_no_imaging_field_id(monkeypatch):
    candidate = build_project_candidate(
        monkeypatch,
        {"hours": 2, "target_hours": 10, "importance": 5},
    )

    assert candidate.imaging_field_id is None


@pytest.mark.parametrize("imaging_field_id", ["unknown", "", 42])
def test_invalid_explicit_project_imaging_field_fails_closed(
    monkeypatch,
    imaging_field_id,
):
    with pytest.raises(ProjectImagingFieldResolutionError):
        build_project_candidate(
            monkeypatch,
            {
                "hours": 2,
                "target_hours": 10,
                "importance": 5,
                "imaging_field_id": imaging_field_id,
            },
        )


def test_project_candidate_reuses_project_imaging_field_resolver(monkeypatch):
    calls = []
    original = astro_score.resolve_project_imaging_field

    def observe(project, resolver):
        calls.append((project, resolver))
        return original(project, resolver)

    monkeypatch.setattr(astro_score, "resolve_project_imaging_field", observe)
    project = {
        "hours": 2,
        "target_hours": 10,
        "importance": 5,
        "imaging_field_id": "sh2-129_ou4",
    }

    candidate = build_project_candidate(monkeypatch, project)

    assert candidate.imaging_field_id == "sh2-129_ou4"
    assert len(calls) == 1
    assert calls[0][0] is project


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
    assert candidates[0].imaging_field_id is None


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


def test_non_positive_project_and_discovery_scores_preserve_rejections():
    result = astro_score.recommend_project_for_night(
        [
            {"name": "Andromeda", "catalog_key": "M31", "global_score": -2},
            {"name": "Orion", "catalog_key": "M42", "score": 0},
        ],
        profile={"projects": {"M31": {}}},
    )

    assert isinstance(result, CandidateBuildResult)
    assert result.candidates == ()
    assert [rejection.target for rejection in result.rejections] == [
        "Andromeda",
        "Orion",
    ]
    assert [rejection.catalog_key for rejection in result.rejections] == [
        "M31",
        "M42",
    ]
    assert [rejection.provenance for rejection in result.rejections] == [
        CandidateProvenance.PROJECT,
        CandidateProvenance.DISCOVERY,
    ]
    assert all(
        rejection.basis
        is CandidateRejectionBasis.NON_POSITIVE_EVALUATION_SCORE
        for rejection in result.rejections
    )
    assert [rejection.evaluation_score for rejection in result.rejections] == [
        -2,
        0,
    ]


def test_candidate_rejection_contract_is_exact_and_immutable():
    assert {basis.value for basis in CandidateRejectionBasis} == {
        "non_positive_evaluation_score", "intent_targets_completed"
    }
    rejection = CandidateRejection(
        target="Orion",
        catalog_key="M42",
        provenance=CandidateProvenance.DISCOVERY,
        basis=CandidateRejectionBasis.NON_POSITIVE_EVALUATION_SCORE,
        evaluation_score=0,
    )

    with pytest.raises(FrozenInstanceError):
        rejection.evaluation_score = 1


def test_missing_score_preserves_exclusion_without_explicit_rejection():
    result = astro_score.recommend_project_for_night(
        [{"name": "Unknown", "catalog_key": "M1"}],
        profile={"projects": {}},
    )

    assert result.candidates == ()
    assert result.rejections == ()


def test_global_score_remains_the_selected_rejection_evidence():
    result = astro_score.recommend_project_for_night(
        [
            {
                "name": "Andromeda",
                "catalog_key": "M31",
                "global_score": -1,
                "score": 80,
            }
        ],
        profile={"projects": {"M31": {}}},
    )

    assert result.candidates == ()
    assert result.rejections[0].evaluation_score == -1
