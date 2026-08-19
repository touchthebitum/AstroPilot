from decision.models.candidate import Candidate
from decision.opportunity.action import Action
from decision.opportunity.opportunity_engine import OpportunityEngine


def make_candidate(
    name: str,
    *,
    decision_score: float,
    final_score: float = 0,
    reasons=None,
    acquired_hours: float = 0,
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