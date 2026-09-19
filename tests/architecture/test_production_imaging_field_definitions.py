import ast
from pathlib import Path

from decision.definitions.production_imaging_fields import (
    CELESTIAL_OBJECT_DEFINITIONS,
    IMAGING_FIELD_DEFINITIONS,
    build_production_imaging_field_resolver,
)


def test_exports_exact_production_objects_and_composite_field():
    assert isinstance(CELESTIAL_OBJECT_DEFINITIONS, tuple)
    assert isinstance(IMAGING_FIELD_DEFINITIONS, tuple)
    assert tuple(
        definition.celestial_object_id
        for definition in CELESTIAL_OBJECT_DEFINITIONS
    ) == ("sh2-129", "ou4")
    assert tuple(
        definition.imaging_field_id
        for definition in IMAGING_FIELD_DEFINITIONS
    ) == ("sh2-129_ou4",)
    assert CELESTIAL_OBJECT_DEFINITIONS[0].object_type == "emission nebula"
    assert CELESTIAL_OBJECT_DEFINITIONS[0].object_subtype == "H II region"
    assert CELESTIAL_OBJECT_DEFINITIONS[1].object_type == "bipolar outflow"
    assert CELESTIAL_OBJECT_DEFINITIONS[1].object_subtype is None

    field = IMAGING_FIELD_DEFINITIONS[0]
    assert tuple(
        component.celestial_object_id for component in field.components
    ) == ("sh2-129", "ou4")


def test_composite_field_has_exact_production_acquisition_intents():
    intents = IMAGING_FIELD_DEFINITIONS[0].acquisition_intents

    assert tuple(intent.acquisition_intent_id for intent in intents) == (
        "sh2-129_ha",
        "ou4_oiii",
    )
    assert tuple(
        (
            intent.acquisition_intent_id,
            intent.filter_type,
            intent.primary_component_ids,
        )
        for intent in intents
    ) == (
        ("sh2-129_ha", "Ha", ("sh2-129",)),
        ("ou4_oiii", "OIII", ("ou4",)),
    )


def test_production_resolver_resolves_exact_field_and_object_ids():
    first = build_production_imaging_field_resolver()
    second = build_production_imaging_field_resolver()

    assert first is not second
    assert first.resolve("sh2-129_ou4") is IMAGING_FIELD_DEFINITIONS[0]
    assert first.resolve_object("sh2-129") is (
        CELESTIAL_OBJECT_DEFINITIONS[0]
    )
    assert first.resolve_object("ou4") is CELESTIAL_OBJECT_DEFINITIONS[1]


def test_production_source_does_not_import_catalog_or_legacy_resolver():
    source_path = (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "definitions"
        / "production_imaging_fields.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "CATALOG" not in imported_names
    assert "LegacyImagingFieldResolver" not in imported_names
