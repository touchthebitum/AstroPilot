from __future__ import annotations

from decision.mission.mission_assembler import MissionAssemblyResult


class TonightMissionService:

    def __init__(
        self,
        build_mission,
        build_mission_with_actionability_diagnostic=None,
    ):
        self.build_mission = build_mission
        self.build_mission_with_actionability_diagnostic = (
            build_mission_with_actionability_diagnostic
        )

    def create(
        self,
        winner,
        objects,
        recommended_key,
        build_mission_input,
    ):
        mission_source = next(
            (
                obj
                for obj in objects
                if obj.get(
                    "catalog_key",
                    obj.get("name"),
                ) == recommended_key
            ),
            None,
        )

        if mission_source is None:
            return None

        evaluation = winner["object_evaluations"].get(
    recommended_key
)

        if evaluation is None:
            return None

        mission_data = {
            "target": mission_source["name"],
            "summary": mission_source["decision_summary"],
            "context": mission_source["decision_context"],
            "mission_input": build_mission_input(
                evaluation
            ),
        }

        return self.build_mission(**mission_data)

    def create_with_actionability_diagnostic(
        self,
        winner,
        objects,
        recommended_key,
        build_mission_input,
    ) -> MissionAssemblyResult:
        if self.build_mission_with_actionability_diagnostic is None:
            return MissionAssemblyResult(
                mission=self.create(
                    winner,
                    objects,
                    recommended_key,
                    build_mission_input,
                )
            )

        mission_source = next(
            (
                obj
                for obj in objects
                if obj.get("catalog_key", obj.get("name")) == recommended_key
            ),
            None,
        )
        if mission_source is None:
            return MissionAssemblyResult(mission=None)

        evaluation = winner["object_evaluations"].get(recommended_key)
        if evaluation is None:
            return MissionAssemblyResult(mission=None)

        result = self.build_mission_with_actionability_diagnostic(
            target=mission_source["name"],
            summary=mission_source["decision_summary"],
            context=mission_source["decision_context"],
            mission_input=build_mission_input(evaluation),
        )
        if not isinstance(result, MissionAssemblyResult):
            raise TypeError("Expected MissionAssemblyResult")
        return result
