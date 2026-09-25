import pytest

from decision.models.acquisition_intent_remaining_progress import (
    AcquisitionIntentRemainingProgress,
)
from decision.models.candidate import Candidate, CandidateProvenance
from decision.opportunity.action import Action
from decision.opportunity.opportunity_engine import OpportunityEngine


def make_candidate(
    name: str,
    *,
    decision_score: float,
    final_score: float = 0,
    reasons=None,
    acquired_hours: float | None = 0,
    provenance: CandidateProvenance = CandidateProvenance.PROJECT,
    intent_progress: tuple[AcquisitionIntentRemainingProgress, ...] = (),
) -> Candidate:
    return Candidate(
        name=name,
        catalog_key=name,
        priority=0,
        astro_score=0,
        final_score=final_score,
        decision_score=decision_score,
        portfolio_score=0,
        global_score=0,
        setup_score=0,
        best_setup=None,
        closure_bonus=0,
        reasons=reasons or [],
        acquired_hours=acquired_hours,
        provenance=provenance,
        acquisition_intent_remaining_progress=intent_progress,
    )


def progress(
    intent_id: str,
    *,
    acquired_hours: float | None,
    target_hours: float,
) -> AcquisitionIntentRemainingProgress:
    return AcquisitionIntentRemainingProgress(
        acquisition_intent_id=intent_id,
        acquired_seconds=(
            acquired_hours * 3600
            if acquired_hours is not None
            else None
        ),
        acquired_hours=acquired_hours,
        target_hours=target_hours,
        remaining_hours=(
            max(target_hours - acquired_hours, 0)
            if acquired_hours is not None
            else None
        ),
    )


def test_returns_none_when_no_candidate_exists():
    engine = OpportunityEngine()

    opportunity = engine.evaluate(
        candidates=[],
    )

    assert opportunity is None


def test_selects_candidate_with_highest_decision_score():
    lower = make_candidate(
        "lower",
        decision_score=80,
        final_score=120,
    )
    higher = make_candidate(
        "higher",
        decision_score=90,
        final_score=100,
    )

    opportunity = OpportunityEngine().evaluate(
        candidates=[lower, higher],
    )

    assert opportunity is not None
    assert opportunity.candidate is higher


def test_preserves_up_to_two_non_winners_in_incoming_order():
    first = make_candidate("first", decision_score=70, final_score=100)
    winner = make_candidate("winner", decision_score=100, final_score=90)
    second = make_candidate("second", decision_score=80, final_score=80)
    omitted = make_candidate("omitted", decision_score=60, final_score=70)

    opportunity = OpportunityEngine().evaluate(
        candidates=[first, winner, second, omitted],
    )

    assert opportunity is not None
    assert opportunity.candidate is winner
    assert opportunity.shortlist_entries == (first, second)
    assert opportunity.shortlist_entries[0] is first
    assert opportunity.shortlist_entries[1] is second


def test_current_action_is_continue_project():
    candidate = make_candidate(
        "M31",
        decision_score=100,
        acquired_hours=1,
    )

    opportunity = OpportunityEngine().evaluate(
        candidates=[candidate],
    )

    assert opportunity is not None
    assert opportunity.action is Action.CONTINUE_PROJECT


def test_candidate_reasons_are_propagated():
    candidate = make_candidate(
        "M31",
        decision_score=100,
        reasons=[
            "Excellent rendement",
            "Projet prioritaire",
        ],
    )

    opportunity = OpportunityEngine().evaluate(
        candidates=[candidate],
    )

    assert opportunity is not None
    assert [
        reason.message
        for reason in opportunity.reasons
    ] == [
        "Excellent rendement",
        "Projet prioritaire",
    ]


def test_starts_project_when_no_hours_are_acquired():
    candidate = make_candidate(
        "Sh2-129",
        decision_score=100,
        acquired_hours=0,
    )

    opportunity = OpportunityEngine().evaluate(
        candidates=[candidate],
    )

    assert opportunity is not None
    assert opportunity.action is Action.START_PROJECT


def test_discovery_with_unknown_acquired_hours_starts_project():
    candidate = make_candidate(
        "M42",
        decision_score=100,
        acquired_hours=None,
    )

    opportunity = OpportunityEngine().evaluate(
        candidates=[candidate],
    )

    assert opportunity is not None
    assert opportunity.candidate is candidate
    assert opportunity.candidate.acquired_hours is None
    assert opportunity.action is Action.START_PROJECT


def test_continues_project_when_hours_are_already_acquired():
    candidate = make_candidate(
        "IC1396",
        decision_score=100,
        acquired_hours=2.5,
    )

    opportunity = OpportunityEngine().evaluate(
        candidates=[candidate],
    )

    assert opportunity is not None
    assert opportunity.action is Action.CONTINUE_PROJECT


def test_modern_positive_progress_overrides_zero_legacy_hours():
    candidate = make_candidate(
        "Sh2-129",
        decision_score=100,
        acquired_hours=0,
        intent_progress=(
            progress("sh2-129_ha", acquired_hours=13.25, target_hours=20),
            progress("ou4_oiii", acquired_hours=5.25, target_hours=25),
        ),
    )

    opportunity = OpportunityEngine().evaluate(candidates=[candidate])

    assert opportunity is not None
    assert opportunity.action is Action.CONTINUE_PROJECT


def test_modern_explicit_zero_progress_starts_project():
    candidate = make_candidate(
        "Sh2-129",
        decision_score=100,
        acquired_hours=8,
        intent_progress=(
            progress("sh2-129_ha", acquired_hours=0, target_hours=20),
            progress("ou4_oiii", acquired_hours=0, target_hours=25),
        ),
    )

    opportunity = OpportunityEngine().evaluate(candidates=[candidate])

    assert opportunity is not None
    assert opportunity.action is Action.START_PROJECT


@pytest.mark.parametrize(
    ("legacy_hours", "expected_action"),
    [
        (2.5, Action.CONTINUE_PROJECT),
        (0, Action.START_PROJECT),
    ],
)
def test_partial_unknown_modern_progress_falls_back_to_legacy(
    legacy_hours,
    expected_action,
):
    candidate = make_candidate(
        "Sh2-129",
        decision_score=100,
        acquired_hours=legacy_hours,
        intent_progress=(
            progress("sh2-129_ha", acquired_hours=0, target_hours=20),
            progress("ou4_oiii", acquired_hours=None, target_hours=25),
        ),
    )

    opportunity = OpportunityEngine().evaluate(candidates=[candidate])

    assert opportunity is not None
    assert opportunity.action is expected_action


def test_discovery_always_starts_even_with_progress_or_legacy_hours():
    candidate = make_candidate(
        "M42",
        decision_score=100,
        acquired_hours=3,
        provenance=CandidateProvenance.DISCOVERY,
        intent_progress=(
            progress("m42_ha", acquired_hours=2, target_hours=10),
        ),
    )

    opportunity = OpportunityEngine().evaluate(candidates=[candidate])

    assert opportunity is not None
    assert opportunity.action is Action.START_PROJECT
