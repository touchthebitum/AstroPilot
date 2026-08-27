import json

from decision.filtering.filter_inventory_loader import (
    FilterInventoryLoader,
)


def write_inventory(path, filter_name):
    path.write_text(
        json.dumps(
            {
                "filters": [
                    {
                        "name": filter_name,
                        "type": "Ha",
                        "bandwidth_nm": 6.5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_default_inventory_uses_configured_user_data_dir(
    tmp_path,
    monkeypatch,
):
    configured_dir = tmp_path / "configured"
    current_dir = tmp_path / "current"
    configured_dir.mkdir()
    current_dir.mkdir()
    write_inventory(
        configured_dir / "user_filters.json",
        "Configured Ha",
    )
    write_inventory(
        current_dir / "user_filters.json",
        "Current Ha",
    )

    monkeypatch.setenv(
        "ASTROPILOT_DATA_DIR",
        str(configured_dir),
    )
    monkeypatch.chdir(current_dir)

    filters = FilterInventoryLoader.load()

    assert [item.name for item in filters] == ["Configured Ha"]


def test_default_inventory_preserves_current_directory_fallback(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("ASTROPILOT_DATA_DIR", raising=False)
    write_inventory(tmp_path / "user_filters.json", "Current Ha")
    monkeypatch.chdir(tmp_path)

    filters = FilterInventoryLoader.load()

    assert [item.name for item in filters] == ["Current Ha"]


def test_missing_configured_inventory_does_not_fall_back_to_current_dir(
    tmp_path,
    monkeypatch,
):
    configured_dir = tmp_path / "configured"
    current_dir = tmp_path / "current"
    configured_dir.mkdir()
    current_dir.mkdir()
    write_inventory(
        current_dir / "user_filters.json",
        "Current Ha",
    )

    monkeypatch.setenv(
        "ASTROPILOT_DATA_DIR",
        str(configured_dir),
    )
    monkeypatch.chdir(current_dir)

    assert FilterInventoryLoader.load() == ()


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
