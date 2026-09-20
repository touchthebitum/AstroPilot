from dataclasses import FrozenInstanceError, fields

import pytest

from decision.models.equipment.filter_optical_profile import (
    FilterOpticalProfile,
)


def _profile(
    filter_profile_id: str = "baader_ha_highspeed_6_5nm",
    filter_type: str = "Ha",
    central_wavelength_nm: float = 656.3,
    fwhm_nm: float = 6.5,
    fast_optics_optimized: bool = True,
) -> FilterOpticalProfile:
    return FilterOpticalProfile(
        filter_profile_id=filter_profile_id,
        filter_type=filter_type,
        central_wavelength_nm=central_wavelength_nm,
        fwhm_nm=fwhm_nm,
        fast_optics_optimized=fast_optics_optimized,
    )


@pytest.mark.parametrize(
    ("filter_type", "central_wavelength_nm"),
    [("Ha", 656.3), ("OIII", 500.7), ("SII", 672.4)],
)
def test_valid_narrowband_profiles_are_immutable(
    filter_type,
    central_wavelength_nm,
):
    profile = _profile(
        filter_profile_id=f"profile_{filter_type}",
        filter_type=filter_type,
        central_wavelength_nm=central_wavelength_nm,
    )

    assert profile.filter_type == filter_type
    assert profile.central_wavelength_nm == central_wavelength_nm
    with pytest.raises((FrozenInstanceError, AttributeError)):
        profile.filter_type = "replacement"


def test_model_has_only_the_five_v1_fields():
    assert tuple(field.name for field in fields(FilterOpticalProfile)) == (
        "filter_profile_id",
        "filter_type",
        "central_wavelength_nm",
        "fwhm_nm",
        "fast_optics_optimized",
    )


@pytest.mark.parametrize("filter_profile_id", ["", "   "])
def test_empty_filter_profile_id_is_rejected(filter_profile_id):
    with pytest.raises(ValueError, match="filter_profile_id"):
        _profile(filter_profile_id=filter_profile_id)


@pytest.mark.parametrize("filter_profile_id", [None, 42, object()])
def test_non_string_filter_profile_id_is_rejected(filter_profile_id):
    with pytest.raises(TypeError, match="filter_profile_id"):
        _profile(filter_profile_id=filter_profile_id)


@pytest.mark.parametrize("filter_type", ["", "   "])
def test_empty_filter_type_is_rejected(filter_type):
    with pytest.raises(ValueError, match="filter_type"):
        _profile(filter_type=filter_type)


@pytest.mark.parametrize("filter_type", [None, 42, object()])
def test_non_string_filter_type_is_rejected(filter_type):
    with pytest.raises(TypeError, match="filter_type"):
        _profile(filter_type=filter_type)


@pytest.mark.parametrize(
    "central_wavelength_nm",
    [True, False, "656.3", None, float("nan"), float("inf"), 0, -1],
)
def test_invalid_central_wavelength_is_rejected(central_wavelength_nm):
    with pytest.raises((TypeError, ValueError), match="central_wavelength_nm"):
        _profile(central_wavelength_nm=central_wavelength_nm)


@pytest.mark.parametrize(
    "fwhm_nm",
    [True, False, "6.5", None, float("nan"), float("-inf"), 0, -1],
)
def test_invalid_fwhm_is_rejected(fwhm_nm):
    with pytest.raises((TypeError, ValueError), match="fwhm_nm"):
        _profile(fwhm_nm=fwhm_nm)


@pytest.mark.parametrize("fast_optics_optimized", [0, 1, "true", None])
def test_non_bool_fast_optics_flag_is_rejected(fast_optics_optimized):
    with pytest.raises(TypeError, match="fast_optics_optimized"):
        _profile(fast_optics_optimized=fast_optics_optimized)


def test_identifiers_are_preserved_without_normalization():
    profile = _profile(
        filter_profile_id=" Profile_Ha ",
        filter_type=" ha ",
    )

    assert profile.filter_profile_id == " Profile_Ha "
    assert profile.filter_type == " ha "
