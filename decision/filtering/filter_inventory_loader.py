import json
import os
from pathlib import Path

from decision.filtering.selected_filter import SelectedFilter


class FilterInventoryLoader:
    @staticmethod
    def load(path: str | Path | None = None) -> tuple[SelectedFilter, ...]:
        if path is None:
            configured_dir = os.environ.get(
                "ASTROPILOT_DATA_DIR"
            )
            path = (
                Path(configured_dir).expanduser()
                / "user_filters.json"
                if configured_dir
                else Path("user_filters.json")
            )
        else:
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
