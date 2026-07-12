from decision.mission.night_mission import NightMission, MissionReason
from decision.risk.risk_engine import RiskEngine
from decision.risk.project_risk_context_builder import ProjectRiskContextBuilder
from decision.night_productivity.night_productivity_engine import NightProductivityEngine
from decision.night_productivity.night_productivity_context import NightProductivityContext
from decision.mission.night_planner import NightPlanner
from decision.intelligence.season_analysis import SeasonAnalysis
from decision.intelligence.analysis_context import AnalysisContext



class MissionAssembler:

    @staticmethod
    def build(
        target,
        summary,
        context,
        equipment,
        timeline,
        alternatives,
        weather=None
    ):

        reasons = []

        for text in summary.positives:
            reasons.append(
                MissionReason(
                    title=text,
                    severity="success",
                )
            )

        for text in summary.negatives:
            reasons.append(
                MissionReason(
                    title=text,
                    severity="warning",
                )
            )

        productivity = NightProductivityEngine.evaluate(
            NightProductivityContext(
                astronomical_hours=6.0,
                cloud_cover=20,
                moon_penalty=0.2,
                altitude_score=8,
                humidity=60,
                wind=5,
                seeing=1.5,
                weather=weather,
                hourly_clouds=None,
                hourly_humidity=None,
                hourly_wind=None,
                hourly_seeing=None,
                hourly_moon_penalty=None,
                )
        )
        
        risk_context = ProjectRiskContextBuilder.build(
            target=target,
            context=context,
        )

        risk = RiskEngine.evaluate(risk_context)
        tasks = NightPlanner.build(productivity)

        analysis_context = AnalysisContext(
            target=target,
            weather=weather,
            productivity=productivity,
            risk=risk,
        )

        season_analysis = SeasonAnalysis.analyze(analysis_context)
        
        return NightMission(
            target=target,
            confidence=summary.confidence,
            reasons=reasons,
            equipment=equipment,
            window_start=None,
            window_end=None,
            recommended_hours=0,
            expected_gain=0,
            alternative_target=None,
            timeline=timeline,
            risk_report=risk,
            season_analysis=season_analysis,
            productivity=productivity,
            tasks=tasks,
            night_slices=productivity.timeline.slices,
        )
    
       