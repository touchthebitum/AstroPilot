from dataclasses import dataclass


@dataclass(frozen=True)
class Mount:
    """
    Represents an astrophotography mount.
    """

    manufacturer: str
    model: str

    payload_capacity_kg: float | None = None

    has_goto: bool = True
    has_guiding: bool = True
