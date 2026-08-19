from decision.engines.project_selection_engine import ProjectSelectionEngine
from decision.models.candidate import Candidate


def make_candidate(
    name: str,
    *,
    final_score: float,
    decision_score: float,
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
    )


def test_candidate_with_highest_final_score_wins():
    high_final = make_candidate(
        "high-final",
        final_score=130,
        decision_score=70,
    )
    high_decision = make_candidate(
        "high-decision",
        final_score=90,
        decision_score=80,
    )

    ranked = ProjectSelectionEngine.rank_candidates(
        [high_final, high_decision]
    )

    assert ranked[0] is high_final

