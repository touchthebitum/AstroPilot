from decision.intelligence.analysis_result import AnalysisResult
from decision.season.season_resolver import SeasonResolver

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
        season = SeasonResolver.resolve(context)

        confidence = season.get("confidence")

        if confidence is None:
            confidence = SeasonAnalysis._compute_confidence(
                season["remaining_days"],
                season["remaining_good_nights"],
            )

        conclusion = SeasonAnalysis._build_conclusion(
            season["urgency"]
        )

        return AnalysisResult(
            analysis_name="SeasonAnalysis",
            conclusion=conclusion,
            confidence=confidence,
            data=season,
        )

