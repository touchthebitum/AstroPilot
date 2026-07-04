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
        )
