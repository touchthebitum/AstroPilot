from dataclasses import dataclass
from decision.filtering.selected_filter import SelectedFilter

@dataclass(frozen=True)
class FilterSelectionContext:
    target_name: str
    target_type: str
    target_subtype: str | None
    available_filters: tuple[SelectedFilter, ...]
    moon_penalty: float
    remaining_hours_by_filter: dict[str, float] | None = None