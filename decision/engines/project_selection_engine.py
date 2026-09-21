from __future__ import annotations

from decision.models.acquisition_intent_selection import (
    AcquisitionIntentSelection,
)
from decision.models.candidate import Candidate, CandidateProvenance
from decision.models.acquisition_intent_remaining_progress import AcquisitionIntentRemainingProgress


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
        priority: float | None,
        astro_score: float,
        final_score: float,
        decision_score: float,
        portfolio_score: float | None,
        global_score: float,
        setup_score: float,
        best_setup: str | None,
        closure_bonus: float | None,
        reasons: list[str],
        strategy_scores: dict[str, float],
        acquired_hours: float | None,
        provenance: CandidateProvenance = CandidateProvenance.PROJECT,
        imaging_field_id: str | None = None,
        acquisition_intent_selection: AcquisitionIntentSelection | None = None,
        acquisition_intent_remaining_progress: tuple[AcquisitionIntentRemainingProgress, ...] = (),
    ) -> Candidate:
        if (
            acquisition_intent_selection is not None
            and not isinstance(
                acquisition_intent_selection,
                AcquisitionIntentSelection,
            )
        ):
            raise TypeError(
                "acquisition_intent_selection must be an "
                "AcquisitionIntentSelection or None"
            )
        return Candidate(
            name=name,
            catalog_key=catalog_key,
            priority=priority,
            astro_score=astro_score,
            final_score=final_score,
            decision_score=decision_score,
            portfolio_score=portfolio_score,
            global_score=global_score,
            setup_score=setup_score,
            best_setup=best_setup,
            closure_bonus=closure_bonus,
            reasons=reasons,
            strategy_scores=strategy_scores,
            acquired_hours=acquired_hours,
            acquisition_intent_remaining_progress=acquisition_intent_remaining_progress,
            provenance=provenance,
            imaging_field_id=imaging_field_id,
            selected_acquisition_intent_id=(
                acquisition_intent_selection.selected_acquisition_intent_id
                if acquisition_intent_selection is not None
                else None
            ),
            viable_acquisition_intent_ids=(
                acquisition_intent_selection.viable_acquisition_intent_ids
                if acquisition_intent_selection is not None
                else ()
            ),
            acquisition_intent_selection_status=(
                acquisition_intent_selection.status
                if acquisition_intent_selection is not None
                else None
            ),
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
