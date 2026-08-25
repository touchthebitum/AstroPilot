import json

from decision.filtering.filter_inventory_loader import (
    FilterInventoryLoader,
)


def test_filter_inventory_loader_builds_selected_filters(tmp_path):
    path = tmp_path / "filters.json"

    path.write_text(
        json.dumps(
            {
                "filters": [
                    {
                        "name": "Baader Ha 6.5nm Highspeed",
                        "type": "Ha",
                        "bandwidth_nm": 6.5,
                    },
                    {
                        "name": "LRGB 1.25",
                        "type": "LRGB",
                        "bandwidth_nm": None,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    filters = FilterInventoryLoader.load(path)

    assert len(filters) == 2

    assert filters[0].name == "Baader Ha 6.5nm Highspeed"
    assert filters[0].filter_type == "Ha"
    assert filters[0].bandwidth_nm == 6.5
    assert filters[0].source == "inventory"

    assert filters[1].filter_type == "LRGB"


def test_filter_inventory_loader_returns_empty_when_file_is_missing(
    tmp_path,
):
    filters = FilterInventoryLoader.load(
        tmp_path / "missing.json"
    )

    assert filters == ()