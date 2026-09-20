import ast
from pathlib import Path

from decision.definitions.production_setup_filter_capabilities import (
    SETUP_FILTER_CAPABILITIES,
    build_production_setup_filter_capabilities_resolver,
)


def test_production_definitions_are_exact_and_immutable():
    assert isinstance(SETUP_FILTER_CAPABILITIES, tuple)
    assert len(SETUP_FILTER_CAPABILITIES) == 1

    capabilities = SETUP_FILTER_CAPABILITIES[0]
    assert capabilities.equipment_id == "samyang_183"
    assert capabilities.available_filter_types == (
        "Ha",
        "OIII",
        "SII",
        "L",
        "R",
        "G",
        "B",
    )
    assert isinstance(capabilities.available_filter_types, tuple)
    assert capabilities.available_filter_profile_ids == (
        "baader_ha_highspeed_6_5nm",
        "baader_oiii_highspeed_6_5nm",
        "baader_sii_highspeed_6_5nm",
    )


def test_production_resolver_resolves_exact_equipment_id():
    first = build_production_setup_filter_capabilities_resolver()
    second = build_production_setup_filter_capabilities_resolver()

    assert first is not second
    assert first.resolve("samyang_183") is SETUP_FILTER_CAPABILITIES[0]


def test_production_source_does_not_import_legacy_or_global_inventory():
    source_path = (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "definitions"
        / "production_setup_filter_capabilities.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "EQUIPMENT_PROFILES" not in imported_names
    assert "FilterInventoryLoader" not in imported_names
