from decision.intelligence.analysis_result import AnalysisResult
from decision.season.season_engine import SeasonEngine
from decision.season.dynamic_season_engine import DynamicSeasonEngine

class SeasonAnalysis:

    @staticmethod
    def _build_conclusion(urgency: str) -> str:
        if urgency == "HIGH":
            return (
                "La saison devient critique. "
                "Ce projet doit être traité en priorité."
            )

        if urgency == "MEDIUM":
            return (
                "La fenêtre saisonnière se réduit. "
                "Reporter ce projet augmente le risque de ne pas le terminer."
            )

        if urgency == "LOW":
            return (
                "La saison reste suffisamment ouverte. "
                "Ce projet peut encore être reporté."
            )

        return (
            "L'urgence saisonnière ne peut pas être déterminée "
            "avec les données disponibles."
        )

    @staticmethod
    def _compute_confidence(
        remaining_days,
        remaining_good_nights,
    ) -> float:
        if remaining_days is None:
            return 0.40

        if remaining_good_nights is None:
            return 0.65

        return 0.90

    @staticmethod
    def analyze(context) -> AnalysisResult:
        dynamic = DynamicSeasonEngine.summary(context)

        if (
            dynamic.remaining_days is None
            or dynamic.remaining_good_nights is None
        ):
            season = SeasonEngine.summary(context.target)
            confidence = SeasonAnalysis._compute_confidence(
                season["remaining_days"],
                season["remaining_good_nights"],
            )
        else:
            season = {
                "target": context.target,
                "start_date": dynamic.start_date,
                "end_date": dynamic.end_date,
                "peak_date": dynamic.peak_date,
                "remaining_days": dynamic.remaining_days,
                "remaining_good_nights": (
                    dynamic.remaining_good_nights
                ),
                "urgency": dynamic.urgency,
                "urgency_score": (
                    100
                    if dynamic.urgency == "HIGH"
                    else 60
                    if dynamic.urgency == "MEDIUM"
                    else 0
                ),
            }
            confidence = dynamic.confidence

        conclusion = SeasonAnalysis._build_conclusion(
            season["urgency"]
        )

        return AnalysisResult(
            analysis_name="SeasonAnalysis",
            conclusion=conclusion,
            confidence=confidence,
            data=season,
        )

