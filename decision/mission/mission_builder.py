from decision.mission.night_mission import (
    NightMission,
    MissionReason,
)
from decision.mission.equipment_builder import EquipmentBuilder

class NightMissionBuilder:

    @staticmethod
    def build(target, summary, context):

        reasons = []

        for r in summary.positives:
            reasons.append(
                MissionReason(
                    title=r,
                    severity="success",
                )
            )

        for r in summary.negatives:
            reasons.append(
                MissionReason(
                    title=r,
                    severity="warning",
                )
            )

        return NightMission(
            target=target,
            confidence=summary.confidence,

            reasons=reasons,
            equipment=EquipmentBuilder.build(context),

            window_start=None,
            window_end=None,
            recommended_hours=0,

            expected_gain=0,
            alternative_target=None,
        )
