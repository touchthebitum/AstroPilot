import pytest

from decision.models.equipment.filter_optical_profile import (
    FilterOpticalProfile,
)
from decision.services.filter_optical_profile_resolver import (
    FilterOpticalProfileResolutionError,
    FilterOpticalProfileResolver,
)


def _profile(
    filter_profile_id: str = "baader_ha_highspeed_6_5nm",
) -> FilterOpticalProfile:
    return FilterOpticalProfile(
        filter_profile_id=filter_profile_id,
        filter_type="Ha",
        central_wavelength_nm=656.3,
        fwhm_nm=6.5,
        fast_optics_optimized=True,
    )


def test_resolves_filter_profile_id_by_exact_key():
    profile = _profile()
    resolver = FilterOpticalProfileResolver([profile])

    assert resolver.resolve("baader_ha_highspeed_6_5nm") is profile


@pytest.mark.parametrize(
    "filter_profile_id",
    ["unknown", "", "   ", None, 42],
)
def test_rejects_unknown_empty_or_non_string_id(filter_profile_id):
    resolver = FilterOpticalProfileResolver([_profile()])

    with pytest.raises(FilterOpticalProfileResolutionError):
        resolver.resolve(filter_profile_id)


@pytest.mark.parametrize(
    "filter_profile_id",
    ["BAADER_HA_HIGHSPEED_6_5NM", " baader_ha_highspeed_6_5nm "],
)
def test_does_not_normalize_lookup_id(filter_profile_id):
    resolver = FilterOpticalProfileResolver([_profile()])

    with pytest.raises(FilterOpticalProfileResolutionError):
        resolver.resolve(filter_profile_id)


def test_case_and_spaces_remain_distinct_profile_ids():
    profiles = [_profile("Profile"), _profile("profile"), _profile(" Profile ")]
    resolver = FilterOpticalProfileResolver(profiles)

    assert [
        resolver.resolve(item.filter_profile_id) for item in profiles
    ] == profiles


def test_does_not_resolve_by_filter_type():
    resolver = FilterOpticalProfileResolver(
        [_profile("first_ha"), _profile("second_ha")]
    )

    with pytest.raises(FilterOpticalProfileResolutionError):
        resolver.resolve("Ha")


def test_rejects_duplicate_filter_profile_ids():
    with pytest.raises(
        FilterOpticalProfileResolutionError,
        match="duplicate filter_profile_id",
    ):
        FilterOpticalProfileResolver([_profile(), _profile()])


def test_rejects_wrong_type_in_collection():
    with pytest.raises(TypeError, match="FilterOpticalProfile"):
        FilterOpticalProfileResolver([object()])


def test_rejects_non_collection_input():
    with pytest.raises(TypeError, match="definitions must be a collection"):
        FilterOpticalProfileResolver(iter(()))


def test_source_collection_mutation_does_not_change_resolver():
    original = _profile()
    definitions = [original]
    resolver = FilterOpticalProfileResolver(definitions)

    definitions.clear()
    definitions.append(_profile("replacement"))

    assert resolver.resolve("baader_ha_highspeed_6_5nm") is original
    with pytest.raises(FilterOpticalProfileResolutionError):
        resolver.resolve("replacement")
