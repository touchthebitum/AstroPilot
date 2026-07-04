from decision.mission.night_mission import NightMission

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
        from decision.risk.risk_engine import RiskEngine

        risk = RiskEngine.evaluate(
            project_priority=90,
            remaining_hours=12,
        )


        return NightMission(
            target=target,
            confidence=summary.confidence,
            reasons=[],
            equipment=equipment,
            window_start=None,
            window_end=None,
            recommended_hours=0,
            expected_gain=0,
            alternative_target=None,
            timeline=timeline,
            risk_report=risk,
        )
