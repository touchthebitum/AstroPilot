from __future__ import annotations


class TonightMissionService:

    def __init__(
        self,
        build_mission,
    ):
        self.build_mission = build_mission

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