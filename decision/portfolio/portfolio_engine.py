from decision.forecast.night_evaluation import NightEvaluation


class PortfolioEngine:

    def enrich(
        self,
        *,
        night_evaluation: NightEvaluation,
    ) -> NightEvaluation:
        return night_evaluation