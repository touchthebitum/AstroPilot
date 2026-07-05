from decision.mission.night_mission import NightMission, MissionReason
from decision.risk.risk_engine import RiskEngine
from decision.risk.project_risk_context_builder import ProjectRiskContextBuilder

class MissionAssembler:

    @staticmethod
    def build(
        target,
        summary,
        context,
        equipment,
        timeline,
        alternatives,
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

        risk_context = ProjectRiskContextBuilder.build(
            target=target,
            context=context,
        )

        risk = RiskEngine.evaluate(risk_context)
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
        )
