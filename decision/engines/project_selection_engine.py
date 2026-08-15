from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
        season_bonus: float,
        altitude_bonus: float,
        roi: float,
        portfolio_score: float,
        global_score: float,
        setup_score: float,
        best_setup: str | None,
        completion_bonus: float,
        closure_bonus: float,
        postponement_risk: float,
        postponement_impact: Mapping[str, Any],
        reasons: dict[str, Any],
        strategy_scores: dict[str, float],
    ) -> Candidate:
        return Candidate(
            name=name,
            catalog_key=catalog_key,
            priority=priority,
            astro_score=astro_score,
            final_score=final_score,
            decision_score=decision_score,
            season_bonus=season_bonus,
            altitude_bonus=altitude_bonus,
            roi=roi,
            portfolio_score=portfolio_score,
            global_score=global_score,
            setup_score=setup_score,
            best_setup=best_setup,
            completion_bonus=completion_bonus,
            closure_bonus=closure_bonus,
            postponement_risk=postponement_risk,
            postponement_penalty=float(
                postponement_impact["postponement_penalty"]
            ),
            urgency_bonus=float(
                postponement_impact["urgency_bonus"]
            ),
            postponement_net_impact=float(
                postponement_impact["postponement_net_impact"]
            ),
            postponement_reason=str(
                postponement_impact["postponement_reason"]
            ),
            reasons=reasons,
            strategy_scores=strategy_scores,
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
