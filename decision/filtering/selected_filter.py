from dataclasses import dataclass


@dataclass(frozen=True)
class SelectedFilter:
    """Compatibility filter description; carries no exact optical profile ID.

    A source label alone never authorizes a modern acquisition-intent mission.
    """

    name: str
    filter_type: str
    bandwidth_nm: float | None = None
    source: str = "selection"