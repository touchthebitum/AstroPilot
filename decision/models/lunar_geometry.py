from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class LunarGeometry:
    """Canonical lunar geometry at one observing instant and site."""

    moon_illumination: float
    moon_altitude_deg: float
    moon_separation_deg: float

    def __post_init__(self) -> None:
        self._validate_bounded_value(
            self.moon_illumination,
            "moon_illumination",
            minimum=0.0,
            maximum=1.0,
        )
        self._validate_bounded_value(
            self.moon_altitude_deg,
            "moon_altitude_deg",
            minimum=-90.0,
            maximum=90.0,
        )
        self._validate_bounded_value(
            self.moon_separation_deg,
            "moon_separation_deg",
            minimum=0.0,
            maximum=180.0,
        )

    @staticmethod
    def _validate_bounded_value(
        value: float,
        name: str,
        *,
        minimum: float,
        maximum: float,
    ) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
        ):
            raise ValueError(f"{name} must be a finite number")
        if not minimum <= value <= maximum:
            raise ValueError(
                f"{name} must satisfy {minimum} <= {name} <= {maximum}"
            )
