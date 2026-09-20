from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class FilterOpticalProfile:
    """Physical optical characteristics of one concrete filter profile."""

    filter_profile_id: str
    filter_type: str
    central_wavelength_nm: float
    fwhm_nm: float
    fast_optics_optimized: bool

    def __post_init__(self) -> None:
        self._validate_non_empty_string(
            self.filter_profile_id,
            "filter_profile_id",
        )
        self._validate_non_empty_string(self.filter_type, "filter_type")
        self._validate_positive_number(
            self.central_wavelength_nm,
            "central_wavelength_nm",
        )
        self._validate_positive_number(self.fwhm_nm, "fwhm_nm")
        if not isinstance(self.fast_optics_optimized, bool):
            raise TypeError("fast_optics_optimized must be a bool")

    @staticmethod
    def _validate_non_empty_string(value: str, name: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must not be empty")

    @staticmethod
    def _validate_positive_number(value: float, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        if not isfinite(float(value)) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
