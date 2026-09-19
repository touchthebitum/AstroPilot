import ast
from pathlib import Path

import pytest

from decision.definitions.production_imaging_field_geometry import (
    IMAGING_FIELD_GEOMETRY_DEFINITIONS,
    build_production_imaging_field_geometry_resolver,
)


def test_production_definitions_are_an_immutable_single_field_tuple():
    assert isinstance(IMAGING_FIELD_GEOMETRY_DEFINITIONS, tuple)
    assert tuple(
        definition.imaging_field_id
        for definition in IMAGING_FIELD_GEOMETRY_DEFINITIONS
    ) == ("sh2-129_ou4",)
    assert not {
        "sh2-129",
        "ou4",
    } & {
        definition.imaging_field_id
        for definition in IMAGING_FIELD_GEOMETRY_DEFINITIONS
    }
    with pytest.raises(TypeError):
        IMAGING_FIELD_GEOMETRY_DEFINITIONS[0] = object()


def test_production_geometry_is_the_composite_field_framing_reference():
    geometry = IMAGING_FIELD_GEOMETRY_DEFINITIONS[0]

    assert geometry.reference_ra_deg == 317.95
    assert geometry.reference_dec_deg == 59.97

    source = _production_source_path().read_text(encoding="utf-8")
    assert "ICRS/J2000 framing/reference center" in source
    assert "not an official object coordinate for Sh2-129 or Ou4" in source


def test_factory_returns_a_fresh_resolver_each_time():
    first = build_production_imaging_field_geometry_resolver()
    second = build_production_imaging_field_geometry_resolver()

    assert first is not second
    assert first.resolve("sh2-129_ou4") is (
        IMAGING_FIELD_GEOMETRY_DEFINITIONS[0]
    )


def test_production_source_has_no_catalog_or_legacy_dependency():
    tree = ast.parse(_production_source_path().read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "CATALOG" not in imported_names
    assert not any(
        "legacy" in name.lower()
        for name in imported_modules | imported_names
    )


def _production_source_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "definitions"
        / "production_imaging_field_geometry.py"
    )
