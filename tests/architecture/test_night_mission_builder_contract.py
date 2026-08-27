from types import SimpleNamespace

import decision.mission.mission_builder as module
from decision.mission.mission_builder import NightMissionBuilder


def test_builder_passes_exact_inputs_to_equipment_and_assembler(
    monkeypatch,
):
    target = "M31"
    summary = SimpleNamespace(
        positives=["Bonne altitude"],
        negatives=["Lune présente"],
    )
    context = SimpleNamespace(site="Jura")
    weather = SimpleNamespace(cloud_cover=15)
    mission_input = SimpleNamespace(recommended_hours=3)
    equipment = ["camera", "mount"]
    mission = SimpleNamespace(target=target)
    captured = {}

    def build_equipment(received_context):
        captured["equipment_context"] = received_context
        return equipment

    def assemble(**kwargs):
        captured["assembler_kwargs"] = kwargs
        return mission

    monkeypatch.setattr(module.EquipmentBuilder, "build", build_equipment)
    monkeypatch.setattr(module.MissionAssembler, "build", assemble)

    result = NightMissionBuilder.build(
        target=target,
        summary=summary,
        context=context,
        weather=weather,
        mission_input=mission_input,
    )

    assert captured["equipment_context"] is context
    assert captured["assembler_kwargs"] == {
        "target": target,
        "summary": summary,
        "context": context,
        "equipment": equipment,
        "alternatives": [],
        "weather": weather,
        "mission_input": mission_input,
    }
    assert result is mission


def test_builder_preserves_none_for_optional_inputs(monkeypatch):
    summary = SimpleNamespace(positives=[], negatives=[])
    captured = {}

    monkeypatch.setattr(
        module.EquipmentBuilder,
        "build",
        lambda context: [],
    )

    def assemble(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(module.MissionAssembler, "build", assemble)

    NightMissionBuilder.build(
        target="M42",
        summary=summary,
        context=object(),
    )

    assert captured["weather"] is None
    assert captured["mission_input"] is None


def test_builder_creates_a_fresh_alternatives_list_each_time(
    monkeypatch,
):
    summary = SimpleNamespace(positives=[], negatives=[])
    alternatives = []

    monkeypatch.setattr(
        module.EquipmentBuilder,
        "build",
        lambda context: [],
    )

    def assemble(**kwargs):
        alternatives.append(kwargs["alternatives"])
        return object()

    monkeypatch.setattr(module.MissionAssembler, "build", assemble)

    for _ in range(2):
        NightMissionBuilder.build(
            target="M31",
            summary=summary,
            context=object(),
        )

    assert alternatives == [[], []]
    assert alternatives[0] is not alternatives[1]


def test_builder_leaves_reason_conversion_to_the_assembler(monkeypatch):
    class ReasonsOwnedByAssembler:
        def __iter__(self):
            raise AssertionError("builder must not iterate mission reasons")

    summary = SimpleNamespace(
        positives=ReasonsOwnedByAssembler(),
        negatives=ReasonsOwnedByAssembler(),
    )
    captured = {}

    monkeypatch.setattr(
        module.EquipmentBuilder,
        "build",
        lambda context: [],
    )

    def assemble(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(module.MissionAssembler, "build", assemble)

    NightMissionBuilder.build(
        target="M31",
        summary=summary,
        context=object(),
    )

    assert captured["summary"] is summary
