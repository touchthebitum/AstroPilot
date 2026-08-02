from collections.abc import Callable

from decision.forecast.night_evaluation import NightEvaluation


class PortfolioEngine:

    def __init__(
        self,
        *,
        project_progress: Callable[[str], float],
    ):
        self.project_progress = project_progress

    def enrich(
        self,
        *,
        night_evaluation: NightEvaluation,
    ) -> NightEvaluation:
        for result in night_evaluation.top3:
            object_name = result["name"]
            result["progress"] = self.project_progress(object_name)

        return night_evaluation
