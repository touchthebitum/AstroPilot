from dataclasses import dataclass


@dataclass(frozen=True)
class SelectedFilter:
    name: str
    filter_type: str
    bandwidth_nm: float | None = None
    source: str = "selection"