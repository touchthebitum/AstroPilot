from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class LunarContaminationEstimate:
    """Relative, spectrally resolved lunar-contamination estimate.

    Rayleigh and Mie indices deliberately remain separate: V1 has no site
    aerosol information with which to assign a physically defensible weight.
    """

    filter_profile_id: str
    lunar_source_factor: float
    rayleigh_relative_index: float
    mie_relative_index: float

    def __post_init__(self) -> None:
        if not isinstance(self.filter_profile_id, str):
            raise TypeError("filter_profile_id must be a string")
        if not self.filter_profile_id.strip():
            raise ValueError("filter_profile_id must not be empty")

        self._validate_non_negative_number(
            self.lunar_source_factor,
            "lunar_source_factor",
        )
        self._validate_non_negative_number(
            self.rayleigh_relative_index,
            "rayleigh_relative_index",
        )
        self._validate_non_negative_number(
            self.mie_relative_index,
            "mie_relative_index",
        )

    @staticmethod
    def _validate_non_negative_number(value: float, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        if not isfinite(float(value)) or value < 0.0:
            raise ValueError(f"{name} must be finite and non-negative")
