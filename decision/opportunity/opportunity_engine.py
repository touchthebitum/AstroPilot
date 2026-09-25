from decision.models.candidate import Candidate, CandidateProvenance

from .action import Action
from .opportunity import Opportunity
from .opportunity_reason_builder import OpportunityReasonBuilder


class OpportunityEngine:

    @staticmethod
    def _resolve_action(candidate: Candidate) -> Action:
        if candidate.provenance is CandidateProvenance.DISCOVERY:
            return Action.START_PROJECT

        targeted_progress = tuple(
            progress
            for progress in candidate.acquisition_intent_remaining_progress
            if progress.target_hours is not None
        )
        if targeted_progress:
            # Completed modern projects are rejected while candidates are built.
            # Keep this boundary defensive without inventing a continuation.
            if all(progress.completed for progress in targeted_progress):
                return Action.START_PROJECT
            if any(
                progress.acquired_hours is not None
                and progress.acquired_hours > 0
                for progress in targeted_progress
            ):
                return Action.CONTINUE_PROJECT
            if all(
                progress.acquired_hours == 0
                for progress in targeted_progress
            ):
                return Action.START_PROJECT

        return (
            Action.CONTINUE_PROJECT
            if (
                candidate.acquired_hours is not None
                and candidate.acquired_hours > 0
            )
            else Action.START_PROJECT
        )

    def evaluate(
        self,
        *,
        candidates: list[Candidate],
    ) -> Opportunity | None:

        if not candidates:
            return None

        best = max(
            candidates,
            key=lambda candidate: candidate.decision_score,
        )

        action = self._resolve_action(best)

        return Opportunity(
            action=action,
            candidate=best,
            reasons=OpportunityReasonBuilder.build(
                candidate=best,
            ),
            shortlist_entries=tuple(
                candidate
                for candidate in candidates
                if candidate is not best
            )[:2],
        )
