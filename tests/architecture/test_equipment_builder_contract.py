from types import SimpleNamespace

from decision.mission.equipment_builder import EquipmentBuilder


def context_with_setup(**setup_fields):
    return SimpleNamespace(
        equipment=SimpleNamespace(
            setup=SimpleNamespace(**setup_fields),
        )
    )


def component(manufacturer, model):
    return SimpleNamespace(manufacturer=manufacturer, model=model)


def test_missing_setup_returns_empty_equipment():
    context = SimpleNamespace(
        equipment=SimpleNamespace(setup=None),
    )

    assert EquipmentBuilder.build(context) == []


def test_empty_setup_returns_empty_equipment():
    assert EquipmentBuilder.build(context_with_setup()) == []


def test_optics_and_camera_are_rendered_in_stable_order():
    context = context_with_setup(
        optics=component("Askar", "FRA400"),
        camera=component("ZWO", "ASI2600MM Pro"),
    )

    assert EquipmentBuilder.build(context) == [
        "🔭 Objectif : Askar FRA400",
        "📷 Caméra : ZWO ASI2600MM Pro",
    ]


def test_telescope_is_used_when_optics_are_absent():
    context = context_with_setup(
        telescope=component("Celestron", "C8"),
        camera=component("ZWO", "ASI533MC Pro"),
    )

    assert EquipmentBuilder.build(context) == [
        "🔭 Télescope : Celestron C8",
        "📷 Caméra : ZWO ASI533MC Pro",
    ]


def test_optics_take_precedence_when_both_optical_fields_exist():
    context = context_with_setup(
        optics=component("Sigma", "135mm"),
        telescope=component("Celestron", "C8"),
    )

    assert EquipmentBuilder.build(context) == [
        "🔭 Objectif : Sigma 135mm",
    ]


def test_camera_can_be_rendered_without_optical_equipment():
    context = context_with_setup(
        camera=component("ZWO", "ASI2600MM Pro"),
    )

    assert EquipmentBuilder.build(context) == [
        "📷 Caméra : ZWO ASI2600MM Pro",
    ]
