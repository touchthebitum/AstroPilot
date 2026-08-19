from __future__ import annotations

from decision.models.candidate import Candidate


class ProjectSelectionEngine:
    """
    Construit et classe les candidats à une session d'astrophotographie.

    Cette première version ne calcule pas encore les scores métier :
    elle reçoit des valeurs déjà calculées par l'orchestrateur.
    """

    @staticmethod
    def build_candidate(
        *,
        name: str,
        catalog_key: str,
        priority: float,
        astro_score: float,
        final_score: float,
        decision_score: float,
        roi: float,
        portfolio_score: float,
        global_score: float,
        setup_score: float,
        best_setup: str | None,
        closure_bonus: float,
        reasons: dict[str],
        strategy_scores: dict[str, float],
        acquired_hours: float,
    ) -> Candidate:
        return Candidate(
            name=name,
            catalog_key=catalog_key,
            priority=priority,
            astro_score=astro_score,
            final_score=final_score,
            decision_score=decision_score,
            roi=roi,
            portfolio_score=portfolio_score,
            global_score=global_score,
            setup_score=setup_score,
            best_setup=best_setup,
            closure_bonus=closure_bonus,
            reasons=reasons,
            strategy_scores=strategy_scores,
            acquired_hours=acquired_hours,
        )

    @staticmethod
    def rank_candidates(
        candidates: list[Candidate],
    ) -> list[Candidate]:
        return sorted(
            candidates,
            key=lambda candidate: candidate.final_score,
            reverse=True,
        )
