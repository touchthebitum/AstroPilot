"""Baader Highspeed 6.5 nm filter profiles currently used by samyang_183."""

from decision.models.equipment.filter_optical_profile import (
    FilterOpticalProfile,
)
from decision.services.filter_optical_profile_resolver import (
    FilterOpticalProfileResolver,
)


FILTER_OPTICAL_PROFILES: tuple[FilterOpticalProfile, ...] = (
    FilterOpticalProfile(
        filter_profile_id="baader_ha_highspeed_6_5nm",
        filter_type="Ha",
        central_wavelength_nm=656.3,
        fwhm_nm=6.5,
        fast_optics_optimized=True,
    ),
    FilterOpticalProfile(
        filter_profile_id="baader_oiii_highspeed_6_5nm",
        filter_type="OIII",
        central_wavelength_nm=500.7,
        fwhm_nm=6.5,
        fast_optics_optimized=True,
    ),
    FilterOpticalProfile(
        filter_profile_id="baader_sii_highspeed_6_5nm",
        filter_type="SII",
        central_wavelength_nm=672.4,
        fwhm_nm=6.5,
        fast_optics_optimized=True,
    ),
)


def build_production_filter_optical_profile_resolver(
) -> FilterOpticalProfileResolver:
    return FilterOpticalProfileResolver(FILTER_OPTICAL_PROFILES)
