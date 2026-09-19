from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class ImagingFieldGeometryDefinition:
    """Reference position for an imaging field in the ICRS/J2000 frame."""

    imaging_field_id: str
    reference_ra_deg: float
    reference_dec_deg: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.imaging_field_id, str)
            or not self.imaging_field_id.strip()
        ):
            raise ValueError("imaging_field_id must be a non-empty string")
        self._validate_coordinate(
            self.reference_ra_deg,
            "reference_ra_deg",
            minimum=0.0,
            maximum=360.0,
            maximum_inclusive=False,
        )
        self._validate_coordinate(
            self.reference_dec_deg,
            "reference_dec_deg",
            minimum=-90.0,
            maximum=90.0,
            maximum_inclusive=True,
        )

    @staticmethod
    def _validate_coordinate(
        value: float,
        name: str,
        *,
        minimum: float,
        maximum: float,
        maximum_inclusive: bool,
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
        ):
            raise ValueError(f"{name} must be a finite number")

        within_upper_bound = (
            value <= maximum if maximum_inclusive else value < maximum
        )
        if value < minimum or not within_upper_bound:
            upper_operator = "<=" if maximum_inclusive else "<"
            raise ValueError(
                f"{name} must satisfy {minimum} <= {name} "
                f"{upper_operator} {maximum}"
            )
