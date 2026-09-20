import ast
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from decision.definitions.production_filter_optical_profiles import (
    build_production_filter_optical_profile_resolver,
)
from decision.definitions.production_imaging_fields import (
    IMAGING_FIELD_DEFINITIONS,
)
from decision.definitions.production_setup_filter_capabilities import (
    SETUP_FILTER_CAPABILITIES,
)
from decision.models.acquisition_intent_filter_profile_resolution import (
    AcquisitionIntentFilterProfileResolution,
    AcquisitionIntentFilterProfileResolutionStatus,
)
from decision.models.equipment.filter_optical_profile import (
    FilterOpticalProfile,
)
from decision.models.equipment.setup_filter_capabilities import (
    SetupFilterCapabilities,
)
from decision.models.imaging_field import AcquisitionIntent
from decision.services.acquisition_intent_filter_profile_resolution import (
    AcquisitionIntentFilterProfileResolutionError,
    resolve_acquisition_intent_filter_profile,
)
from decision.services.filter_optical_profile_resolver import (
    FilterOpticalProfileResolver,
)


def _intent(filter_type: str = "Ha") -> AcquisitionIntent:
    return AcquisitionIntent("intent", filter_type, ("component",))


def _profile(
    filter_profile_id: str,
    filter_type: str = "Ha",
) -> FilterOpticalProfile:
    return FilterOpticalProfile(
        filter_profile_id=filter_profile_id,
        filter_type=filter_type,
        central_wavelength_nm=656.3,
        fwhm_nm=6.5,
        fast_optics_optimized=True,
    )


def _resolve(
    intent: AcquisitionIntent,
    capabilities: SetupFilterCapabilities,
    *profiles: FilterOpticalProfile,
) -> AcquisitionIntentFilterProfileResolution:
    return resolve_acquisition_intent_filter_profile(
        intent,
        capabilities,
        FilterOpticalProfileResolver(profiles),
    )


def test_result_contract_is_exact_frozen_and_typed():
    result = AcquisitionIntentFilterProfileResolution(
        "intent",
        AcquisitionIntentFilterProfileResolutionStatus.RESOLVED,
        ("ha",),
    )

    assert tuple(field.name for field in fields(result)) == (
        "acquisition_intent_id",
        "status",
        "matching_filter_profile_ids",
    )
    with pytest.raises(FrozenInstanceError):
        result.status = AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE


def test_status_enum_has_exactly_the_three_v1_states():
    assert tuple(AcquisitionIntentFilterProfileResolutionStatus) == (
        AcquisitionIntentFilterProfileResolutionStatus.RESOLVED,
        AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE,
        AcquisitionIntentFilterProfileResolutionStatus.AMBIGUOUS,
    )


@pytest.mark.parametrize(
    ("status", "matches"),
    (
        (AcquisitionIntentFilterProfileResolutionStatus.RESOLVED, ()),
        (AcquisitionIntentFilterProfileResolutionStatus.RESOLVED, ("a", "b")),
        (AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE, ("a",)),
        (AcquisitionIntentFilterProfileResolutionStatus.AMBIGUOUS, ()),
        (AcquisitionIntentFilterProfileResolutionStatus.AMBIGUOUS, ("a",)),
    ),
)
def test_result_rejects_status_cardinality_mismatches(status, matches):
    with pytest.raises(ValueError):
        AcquisitionIntentFilterProfileResolution("intent", status, matches)


@pytest.mark.parametrize(
    "build",
    (
        lambda: AcquisitionIntentFilterProfileResolution(
            42,
            AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE,
            (),
        ),
        lambda: AcquisitionIntentFilterProfileResolution(
            " ",
            AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE,
            (),
        ),
        lambda: AcquisitionIntentFilterProfileResolution("intent", "resolved", ()),
        lambda: AcquisitionIntentFilterProfileResolution(
            "intent",
            AcquisitionIntentFilterProfileResolutionStatus.RESOLVED,
            ["ha"],
        ),
        lambda: AcquisitionIntentFilterProfileResolution(
            "intent",
            AcquisitionIntentFilterProfileResolutionStatus.RESOLVED,
            (42,),
        ),
        lambda: AcquisitionIntentFilterProfileResolution(
            "intent",
            AcquisitionIntentFilterProfileResolutionStatus.AMBIGUOUS,
            ("ha", "ha"),
        ),
    ),
)
def test_result_rejects_invalid_field_values(build):
    with pytest.raises((TypeError, ValueError)):
        build()


def test_resolved_when_exactly_one_setup_profile_matches():
    result = _resolve(
        _intent("Ha"),
        SetupFilterCapabilities("setup", ("Ha",), ("ha", "oiii")),
        _profile("ha", "Ha"),
        _profile("oiii", "OIII"),
    )

    assert result == AcquisitionIntentFilterProfileResolution(
        "intent",
        AcquisitionIntentFilterProfileResolutionStatus.RESOLVED,
        ("ha",),
    )


def test_unavailable_when_no_setup_profile_matches():
    result = _resolve(
        _intent("SII"),
        SetupFilterCapabilities("setup", ("SII",), ("ha", "oiii")),
        _profile("ha", "Ha"),
        _profile("oiii", "OIII"),
    )

    assert result.status is AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE
    assert result.matching_filter_profile_ids == ()


def test_ambiguous_when_multiple_setup_profiles_match_in_setup_order():
    result = _resolve(
        _intent("Ha"),
        SetupFilterCapabilities(
            "setup",
            ("Ha",),
            ("second-ha", "oiii", "first-ha"),
        ),
        _profile("first-ha", "Ha"),
        _profile("second-ha", "Ha"),
        _profile("oiii", "OIII"),
    )

    assert result.status is AcquisitionIntentFilterProfileResolutionStatus.AMBIGUOUS
    assert result.matching_filter_profile_ids == ("second-ha", "first-ha")


@pytest.mark.parametrize(
    ("intent", "capabilities", "resolver"),
    (
        (
            object(),
            SetupFilterCapabilities("setup", ("Ha",)),
            FilterOpticalProfileResolver(()),
        ),
        (_intent(), object(), FilterOpticalProfileResolver(())),
        (_intent(), SetupFilterCapabilities("setup", ("Ha",)), object()),
    ),
)
def test_rejects_wrong_input_types(intent, capabilities, resolver):
    with pytest.raises(TypeError):
        resolve_acquisition_intent_filter_profile(
            intent,
            capabilities,
            resolver,
        )


@pytest.mark.parametrize(
    "filter_profile_id",
    ("unknown", "KNOWN", " known "),
)
def test_unknown_or_normalized_setup_profile_id_fails_closed(
    filter_profile_id,
):
    with pytest.raises(
        AcquisitionIntentFilterProfileResolutionError,
        match="unresolvable filter_profile_id",
    ):
        _resolve(
            _intent(),
            SetupFilterCapabilities(
                "setup",
                ("Ha",),
                ("known", filter_profile_id),
            ),
            _profile("known"),
        )


def test_profile_with_different_type_is_not_a_match():
    result = _resolve(
        _intent("Ha"),
        SetupFilterCapabilities("setup", ("Ha",), ("oiii",)),
        _profile("oiii", "OIII"),
    )

    assert result.status is AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE


@pytest.mark.parametrize(
    ("intent_filter_type", "profile_filter_type"),
    (("Ha", "ha"), ("Ha", " Ha "), (" Ha ", "Ha")),
)
def test_filter_type_matching_does_not_normalize_case_or_spaces(
    intent_filter_type,
    profile_filter_type,
):
    result = _resolve(
        _intent(intent_filter_type),
        SetupFilterCapabilities(
            "setup",
            (intent_filter_type,),
            ("profile",),
        ),
        _profile("profile", profile_filter_type),
    )

    assert result.status is AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE


def test_available_filter_types_never_act_as_a_fallback():
    result = _resolve(
        _intent("Ha"),
        SetupFilterCapabilities("setup", ("Ha",), ()),
        _profile("unreferenced-ha", "Ha"),
    )

    assert result == AcquisitionIntentFilterProfileResolution(
        "intent",
        AcquisitionIntentFilterProfileResolutionStatus.UNAVAILABLE,
        (),
    )


def test_available_filter_types_do_not_gate_an_exact_profile_match():
    result = _resolve(
        _intent("Ha"),
        SetupFilterCapabilities("setup", ("OIII",), ("ha",)),
        _profile("ha", "Ha"),
    )

    assert result.status is AcquisitionIntentFilterProfileResolutionStatus.RESOLVED
    assert result.matching_filter_profile_ids == ("ha",)


@pytest.mark.parametrize(
    ("intent_index", "expected_profile_id"),
    (
        (0, "baader_ha_highspeed_6_5nm"),
        (1, "baader_oiii_highspeed_6_5nm"),
    ),
)
def test_production_samyang_183_resolves_ha_and_oiii(
    intent_index,
    expected_profile_id,
):
    result = resolve_acquisition_intent_filter_profile(
        IMAGING_FIELD_DEFINITIONS[0].acquisition_intents[intent_index],
        SETUP_FILTER_CAPABILITIES[0],
        build_production_filter_optical_profile_resolver(),
    )

    assert result.status is AcquisitionIntentFilterProfileResolutionStatus.RESOLVED
    assert result.matching_filter_profile_ids == (expected_profile_id,)


def test_production_samyang_183_resolves_synthetic_sii_intent():
    result = resolve_acquisition_intent_filter_profile(
        _intent("SII"),
        SETUP_FILTER_CAPABILITIES[0],
        build_production_filter_optical_profile_resolver(),
    )

    assert result.matching_filter_profile_ids == (
        "baader_sii_highspeed_6_5nm",
    )


def test_service_has_no_selection_lunar_mission_or_session_dependency():
    source_path = (
        Path(__file__).resolve().parents[2]
        / "decision"
        / "services"
        / "acquisition_intent_filter_profile_resolution.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
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

    assert "FilterSelectionEngine" not in imported_names
    assert not any(
        forbidden in module
        for module in imported_modules
        for forbidden in (
            "filter_selection",
            "lunar",
            "mission",
            "session",
        )
    )
