from types import SimpleNamespace

from decision.services.tonight_mission_service import TonightMissionService
from decision.mission.mission_assembler import MissionAssemblyResult
from decision.services.session_availability_windowing import (
    ActionabilityRefusal,
    ActionabilityRefusalConclusion,
    ActionabilityRefusalStatus,
)


class RecordingMissionBuilder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(**kwargs)


class RecordingInputBuilder:
    def __init__(self):
        self.calls = []

    def __call__(self, evaluation):
        self.calls.append(evaluation)
        return SimpleNamespace(source=evaluation)


def make_object(*, name="Andromeda", catalog_key="M31"):
    return {
        "name": name,
        "catalog_key": catalog_key,
        "decision_summary": SimpleNamespace(label="excellent"),
        "decision_context": SimpleNamespace(quality=90),
    }


def test_catalog_key_selects_source_and_evaluation():
    source = make_object()
    evaluation = SimpleNamespace(score=95)
    mission_builder = RecordingMissionBuilder()
    input_builder = RecordingInputBuilder()
    service = TonightMissionService(build_mission=mission_builder)

    mission = service.create(
        winner={"object_evaluations": {"M31": evaluation}},
        objects=[make_object(name="Orion", catalog_key="M42"), source],
        recommended_key="M31",
        build_mission_input=input_builder,
    )

    assert input_builder.calls == [evaluation]
    assert mission_builder.calls == [
        {
            "target": "Andromeda",
            "summary": source["decision_summary"],
            "context": source["decision_context"],
            "mission_input": mission.mission_input,
        }
    ]
    assert mission.mission_input.source is evaluation


def test_object_name_is_used_when_catalog_key_is_missing():
    source = make_object(name="M31")
    source.pop("catalog_key")
    evaluation = SimpleNamespace(score=80)
    mission_builder = RecordingMissionBuilder()
    input_builder = RecordingInputBuilder()
    service = TonightMissionService(build_mission=mission_builder)

    mission = service.create(
        winner={"object_evaluations": {"M31": evaluation}},
        objects=[source],
        recommended_key="M31",
        build_mission_input=input_builder,
    )

    assert mission.target == "M31"
    assert input_builder.calls == [evaluation]


def test_unknown_recommended_object_stops_before_input_building():
    mission_builder = RecordingMissionBuilder()
    input_builder = RecordingInputBuilder()
    service = TonightMissionService(build_mission=mission_builder)

    mission = service.create(
        winner={"object_evaluations": {}},
        objects=[make_object()],
        recommended_key="M42",
        build_mission_input=input_builder,
    )

    assert mission is None
    assert input_builder.calls == []
    assert mission_builder.calls == []


def test_missing_evaluation_stops_before_input_building():
    mission_builder = RecordingMissionBuilder()
    input_builder = RecordingInputBuilder()
    service = TonightMissionService(build_mission=mission_builder)

    mission = service.create(
        winner={"object_evaluations": {}},
        objects=[make_object()],
        recommended_key="M31",
        build_mission_input=input_builder,
    )

    assert mission is None
    assert input_builder.calls == []
    assert mission_builder.calls == []


def test_matching_uses_catalog_key_before_display_name():
    misleading = make_object(name="M31", catalog_key="M42")
    selected = make_object(name="Andromeda", catalog_key="M31")
    mission_builder = RecordingMissionBuilder()
    service = TonightMissionService(build_mission=mission_builder)

    mission = service.create(
        winner={"object_evaluations": {"M31": object()}},
        objects=[misleading, selected],
        recommended_key="M31",
        build_mission_input=lambda evaluation: evaluation,
    )

    assert mission.target == "Andromeda"


def test_diagnostic_builder_preserves_authoritative_refusal():
    source = make_object()
    evaluation = SimpleNamespace(score=95)
    refusal = ActionabilityRefusal(
        conclusion=ActionabilityRefusalConclusion.NO_PRODUCTIVE_WINDOW,
        status=ActionabilityRefusalStatus.CONSTRAINTS_REFUSAL,
        cause_code="insufficient_actionable_productive_window",
        best_productive_window_minutes=59.0,
        required_continuous_minutes=60,
    )

    def diagnostic_builder(**kwargs):
        return MissionAssemblyResult(None, refusal)

    service = TonightMissionService(
        build_mission=lambda **kwargs: None,
        build_mission_with_actionability_diagnostic=diagnostic_builder,
    )

    result = service.create_with_actionability_diagnostic(
        winner={"object_evaluations": {"M31": evaluation}},
        objects=[source],
        recommended_key="M31",
        build_mission_input=lambda value: value,
    )

    assert result.mission is None
    assert result.actionability_refusal is refusal
