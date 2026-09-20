import ast
from pathlib import Path

import pytest

from decision.definitions.production_filter_optical_profiles import (
    build_production_filter_optical_profile_resolver,
)
from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.services.setup_filter_profile_references import (
    SetupFilterProfileReferenceValidationError,
    validate_setup_filter_profile_references,
)


KNOWN_PROFILE_IDS = (
    "baader_ha_highspeed_6_5nm",
    "baader_oiii_highspeed_6_5nm",
    "baader_sii_highspeed_6_5nm",
)


def test_accepts_all_known_baader_profile_references():
    capabilities = SetupFilterCapabilities(
        "samyang_183",
        ("Ha", "OIII", "SII", "L", "R", "G", "B"),
        KNOWN_PROFILE_IDS,
    )

    assert (
        validate_setup_filter_profile_references(
            capabilities,
            build_production_filter_optical_profile_resolver(),
        )
        is None
    )


def test_empty_profile_references_remain_valid_for_legacy_definitions():
    capabilities = SetupFilterCapabilities("legacy", ("L",))

    assert (
        validate_setup_filter_profile_references(
            capabilities,
            build_production_filter_optical_profile_resolver(),
        )
        is None
    )


@pytest.mark.parametrize(
    "filter_profile_id",
    ["unknown", "BAADER_HA_HIGHSPEED_6_5NM", " baader_ha_highspeed_6_5nm "],
)
def test_rejects_unknown_profile_id_without_normalization(filter_profile_id):
    capabilities = SetupFilterCapabilities(
        "samyang_183",
        ("Ha",),
        (filter_profile_id,),
    )

    with pytest.raises(
        SetupFilterProfileReferenceValidationError,
        match="unresolvable filter_profile_id",
    ):
        validate_setup_filter_profile_references(
            capabilities,
            build_production_filter_optical_profile_resolver(),
        )


def test_rejects_known_profile_when_filter_type_is_not_available():
    capabilities = SetupFilterCapabilities(
        "samyang_183",
        ("OIII",),
        ("baader_ha_highspeed_6_5nm",),
    )

    with pytest.raises(
        SetupFilterProfileReferenceValidationError,
        match="filter profile type is not available on setup",
    ):
        validate_setup_filter_profile_references(
            capabilities,
            build_production_filter_optical_profile_resolver(),
        )


def test_validator_source_has_no_selection_or_eligibility_dependency():
    source_path = (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "services"
        / "setup_filter_profile_references.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "FilterSelectionEngine" not in imported_names
    assert "AcquisitionIntentEligibility" not in imported_names
