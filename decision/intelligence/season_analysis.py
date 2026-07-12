from decision.intelligence.analysis_result import AnalysisResult
from decision.season.season_engine import SeasonEngine


class SeasonAnalysis:

    @staticmethod
    def analyze(context) -> AnalysisResult:

        season = SeasonEngine.summary(context.target)

        return AnalysisResult(
            analysis_name="SeasonAnalysis",
            conclusion=f"Saison : {season['urgency']}",
            confidence=0.90,
            data=season,
        )