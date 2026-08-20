from collections.abc import Callable

from decision.forecast.night_evaluation import NightEvaluation


class PortfolioEngine:

    def __init__(
        self,
        *,
        project_progress: Callable[[str], float],
        project_remaining_hours: Callable[[str], float | None],
        project_priority: Callable[[str], float],
        get_projects: Callable[[], dict],
    ):
        self.project_progress = project_progress
        self.project_remaining_hours = project_remaining_hours
        self.project_priority = project_priority
        self.get_projects = get_projects

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

    def _build_top_objects(
        self,
        *,
        night_evaluation: NightEvaluation,
    ) -> None:
        portfolio_keys = set(
            self.get_projects().keys()
        )

        top_objects_for_night = (
            night_evaluation.all_results[:5]
        )

        portfolio_objects = [
            result
            for result in night_evaluation.all_results
            if result.get(
                "catalog_key",
                result.get("name"),
            ) in portfolio_keys
        ]

        for result in portfolio_objects:
            if result not in top_objects_for_night:
                top_objects_for_night.append(result)

        night_evaluation.top_objects_for_night = (
            top_objects_for_night
        )
