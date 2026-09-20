import ast
from pathlib import Path

import pytest

from decision.definitions.production_filter_optical_profiles import (
    FILTER_OPTICAL_PROFILES,
    build_production_filter_optical_profile_resolver,
)


EXPECTED_PROFILES = {
    "baader_ha_highspeed_6_5nm": ("Ha", 656.3, 6.5, True),
    "baader_oiii_highspeed_6_5nm": ("OIII", 500.7, 6.5, True),
    "baader_sii_highspeed_6_5nm": ("SII", 672.4, 6.5, True),
}


def test_production_definitions_are_an_immutable_tuple():
    assert isinstance(FILTER_OPTICAL_PROFILES, tuple)
    with pytest.raises(TypeError):
        FILTER_OPTICAL_PROFILES[0] = object()


def test_production_profiles_exactly_describe_current_baader_filters():
    actual = {
        profile.filter_profile_id: (
            profile.filter_type,
            profile.central_wavelength_nm,
            profile.fwhm_nm,
            profile.fast_optics_optimized,
        )
        for profile in FILTER_OPTICAL_PROFILES
    }

    assert actual == EXPECTED_PROFILES
    assert "Baader Highspeed 6.5 nm" in _source_path().read_text(
        encoding="utf-8"
    )


def test_factory_returns_a_fresh_exact_resolver_each_time():
    first = build_production_filter_optical_profile_resolver()
    second = build_production_filter_optical_profile_resolver()

    assert first is not second
    for profile in FILTER_OPTICAL_PROFILES:
        assert first.resolve(profile.filter_profile_id) is profile


def test_production_source_has_no_setup_selection_or_catalog_dependency():
    tree = ast.parse(_source_path().read_text(encoding="utf-8"))
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

    assert "SetupFilterCapabilities" not in imported_names
    assert "FilterSelectionEngine" not in imported_names
    assert "CATALOG" not in imported_names
    assert not any(
        forbidden in module
        for module in imported_modules
        for forbidden in (
            "setup_filter_capabilities",
            "filter_selection_engine",
            "catalog",
        )
    )


def _source_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "definitions"
        / "production_filter_optical_profiles.py"
    )
