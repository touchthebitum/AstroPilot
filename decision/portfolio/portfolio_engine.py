from collections.abc import Callable

from decision.forecast.night_evaluation import NightEvaluation


class PortfolioEngine:

    def __init__(
        self,
        *,
        project_progress: Callable[[str], float],
        project_remaining_hours: Callable[[str], float | None],
        project_priority: Callable[[str], float],
        project_roi: Callable[[str], float],
    ):
        self.project_progress = project_progress
        self.project_remaining_hours = project_remaining_hours
        self.project_priority = project_priority
        self.project_roi = project_roi

    def enrich(
        self,
        *,
        night_evaluation: NightEvaluation,
    ) -> NightEvaluation:
        self._enrich_project_state(
            night_evaluation=night_evaluation,
        )

        self._enrich_decision_metrics(
            night_evaluation=night_evaluation,
        )

        self._build_top_objects(
            night_evaluation=night_evaluation,
        )

        return night_evaluation

    def _enrich_project_state(
        self,
        *,
        night_evaluation: NightEvaluation,
    ) -> None:
        for result in night_evaluation.top3:
            object_name = result["name"]

            result["progress"] = self.project_progress(
                object_name
            )

            result["remaining_hours"] = (
                self.project_remaining_hours(
                    object_name
                )
            )

    def _enrich_decision_metrics(
        self,
        *,
        night_evaluation: NightEvaluation,
    ) -> None:
        for result in night_evaluation.top3:
            object_name = result["name"]

            result["priority"] = self.project_priority(
                object_name
            )

            result["roi"] = self.project_roi(
                object_name
            )

    def _build_top_objects(
        self,
        *,
        night_evaluation: NightEvaluation,
    ) -> None:
        top_objects_for_night = (
            night_evaluation.all_results[:5]
        )

        night_evaluation.top_objects_for_night = (
            top_objects_for_night
        )
