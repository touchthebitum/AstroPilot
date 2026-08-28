from decision.forecast.night_evaluation import NightEvaluation


class PortfolioEngine:

    def enrich(
        self,
        *,
        night_evaluation: NightEvaluation,
        projects: dict,
    ) -> NightEvaluation:
        self._build_top_objects(
            night_evaluation=night_evaluation,
            projects=projects,
        )

        return night_evaluation


    def _build_top_objects(
        self,
        *,
        night_evaluation: NightEvaluation,
        projects: dict,
    ) -> None:
        portfolio_keys = set(
            projects.keys()
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
