import json
from pathlib import Path

from decision.filtering.selected_filter import SelectedFilter


class FilterInventoryLoader:
    @staticmethod
    def load(path: str | Path = "user_filters.json") -> tuple[SelectedFilter, ...]:
        path = Path(path)

        if not path.exists():
            return ()

        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        filters = []

        for raw_filter in data.get("filters", []):
            name = raw_filter.get("name")
            filter_type = raw_filter.get("type")

            if not name or not filter_type:
                continue

            filters.append(
                SelectedFilter(
                    name=name,
                    filter_type=filter_type,
                    bandwidth_nm=raw_filter.get("bandwidth_nm"),
                    source="inventory",
                )
            )

        return tuple(filters)