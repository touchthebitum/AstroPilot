from decision.mission.night_mission import (
    NightMission,
    MissionReason,
    MissionEvent,
)
from decision.mission.equipment_builder import EquipmentBuilder
from decision.mission.mission_assembler import MissionAssembler
from decision.mission.timeline_builder import TimelineBuilder

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

        from decision.mission.timeline_builder import TimelineBuilder

        equipment = EquipmentBuilder.build(context)
        timeline = []
        alternatives = []

        return MissionAssembler.build(
        target=target,
        summary=summary,
        context=context,
        equipment=equipment,
        timeline=timeline,
        alternatives=alternatives,
    )