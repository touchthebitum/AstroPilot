from decision.mission.night_mission import MissionReason
from decision.mission.equipment_builder import EquipmentBuilder
from decision.mission.mission_assembler import MissionAssembler
from decision.mission.mission_input import MissionInput
from decision.weather.weather_forecast import WeatherForecast


class NightMissionBuilder:

    @staticmethod
    def build(
        target,
        summary,
        context,
        weather: WeatherForecast | None = None,
        mission_input: MissionInput | None = None,
    ):

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
            weather=weather,
            mission_input=mission_input,
        )
