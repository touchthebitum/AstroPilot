from math import acos, cos, degrees, radians, sin

from decision.models.equipment.filter_optical_profile import (
    FilterOpticalProfile,
)
from decision.models.intent_night_evidence import IntentNightEvidence
from decision.models.lunar_contamination_estimate import (
    LunarContaminationEstimate,
)


# Stable internal references make both indices dimensionless and comparable.
# A value of 1 corresponds to a 550 nm, 1 nm-wide filter with a full Moon at
# zenith and zero Moon-field separation, independently for each component.
_REFERENCE_WAVELENGTH_NM = 550.0
_REFERENCE_BANDWIDTH_NM = 1.0
_RAYLEIGH_WAVELENGTH_EXPONENT = 4.0
_MIE_WAVELENGTH_EXPONENT = 1.3
_RAYLEIGH_PHASE_OFFSET = 1.06


class LunarContaminationEstimationError(ValueError):
    """Raised when V1 cannot safely estimate lunar contamination."""


class IncompleteLunarEvidenceError(LunarContaminationEstimationError):
    """Raised when one or more required lunar evidence values are absent."""


class LunarContaminationEstimator:
    """Estimate separate relative Rayleigh and Mie lunar contamination.

    This V1 is not an absolute sky-brightness or SQM model. Moon altitude at
    or below the horizon is explicitly approximated as zero contamination.
    No atmospheric extinction, aerosol weighting, or combined score is used.
    """

    def estimate(
        self,
        evidence: IntentNightEvidence,
        filter_profile: FilterOpticalProfile,
    ) -> LunarContaminationEstimate:
        if not isinstance(evidence, IntentNightEvidence):
            raise LunarContaminationEstimationError(
                "evidence must be an IntentNightEvidence"
            )
        if not isinstance(filter_profile, FilterOpticalProfile):
            raise LunarContaminationEstimationError(
                "filter_profile must be a FilterOpticalProfile"
            )

        illumination = evidence.moon_illumination
        altitude_deg = evidence.moon_altitude_deg
        separation_deg = evidence.moon_separation_deg
        if (
            illumination is None
            or altitude_deg is None
            or separation_deg is None
        ):
            raise IncompleteLunarEvidenceError(
                "moon_illumination, moon_altitude_deg, and "
                "moon_separation_deg are required"
            )

        if altitude_deg <= 0.0:
            return LunarContaminationEstimate(
                filter_profile_id=filter_profile.filter_profile_id,
                lunar_source_factor=0.0,
                rayleigh_relative_index=0.0,
                mie_relative_index=0.0,
            )

        lunar_source_factor = self._lunar_source_factor(illumination)
        altitude_factor = sin(radians(altitude_deg))
        bandwidth_factor = filter_profile.fwhm_nm / _REFERENCE_BANDWIDTH_NM

        wavelength_ratio = (
            _REFERENCE_WAVELENGTH_NM / filter_profile.central_wavelength_nm
        )
        rayleigh_spectral_factor = (
            wavelength_ratio ** _RAYLEIGH_WAVELENGTH_EXPONENT
        )
        mie_spectral_factor = wavelength_ratio ** _MIE_WAVELENGTH_EXPONENT

        separation_rad = radians(separation_deg)
        rayleigh_angular_factor = (
            _RAYLEIGH_PHASE_OFFSET + cos(separation_rad) ** 2
        ) / (_RAYLEIGH_PHASE_OFFSET + 1.0)

        # The large-angle Mie term in the Krisciunas-Schaefer formulation is
        # proportional to 10^(-rho/40), with rho in degrees. V1 uses that
        # stable, finite term across the full domain and normalizes it at 0°;
        # it intentionally omits the singular empirical near-Moon branch.
        mie_angular_factor = 10.0 ** (-separation_deg / 40.0)

        common_factor = (
            lunar_source_factor * altitude_factor * bandwidth_factor
        )
        return LunarContaminationEstimate(
            filter_profile_id=filter_profile.filter_profile_id,
            lunar_source_factor=lunar_source_factor,
            rayleigh_relative_index=(
                common_factor
                * rayleigh_angular_factor
                * rayleigh_spectral_factor
            ),
            mie_relative_index=(
                common_factor * mie_angular_factor * mie_spectral_factor
            ),
        )

    @staticmethod
    def _lunar_source_factor(illumination: float) -> float:
        phase_cosine = min(1.0, max(-1.0, 2.0 * illumination - 1.0))
        phase_angle_deg = degrees(acos(phase_cosine))

        # Krisciunas-Schaefer lunar phase law, divided by its full-Moon value.
        # The constant 3.84 magnitude term therefore cancels. The result is
        # dimensionless, equals 1 at full Moon, and approaches zero toward new.
        relative_magnitude = (
            0.026 * phase_angle_deg
            + 4.0e-9 * phase_angle_deg ** 4
        )
        return 10.0 ** (-0.4 * relative_magnitude)
