import json

import pytest

import decision.filtering.filter_inventory_loader as loader_module
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


def test_default_inventory_is_canonical_and_independent_of_current_directory(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "canonical"
    first_cwd = tmp_path / "first"
    second_cwd = tmp_path / "second"
    data_root.mkdir()
    first_cwd.mkdir()
    second_cwd.mkdir()
    write_inventory(data_root / "user_filters.json", "Canonical Ha")
    write_inventory(first_cwd / "user_filters.json", "First CWD Ha")
    write_inventory(second_cwd / "user_filters.json", "Second CWD Ha")
    monkeypatch.setattr(loader_module, "get_user_data_dir", lambda: data_root)

    monkeypatch.chdir(first_cwd)
    first = FilterInventoryLoader.load()
    monkeypatch.chdir(second_cwd)
    second = FilterInventoryLoader.load()

    assert [item.name for item in first] == ["Canonical Ha"]
    assert [item.name for item in second] == ["Canonical Ha"]


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


def test_missing_default_inventory_does_not_fabricate_filters(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "canonical"
    current_dir = tmp_path / "current"
    data_root.mkdir()
    current_dir.mkdir()
    write_inventory(current_dir / "user_filters.json", "Current Ha")
    monkeypatch.setattr(loader_module, "get_user_data_dir", lambda: data_root)
    monkeypatch.chdir(current_dir)

    assert FilterInventoryLoader.load() == ()


def test_invalid_default_inventory_preserves_json_error(tmp_path, monkeypatch):
    data_root = tmp_path / "canonical"
    data_root.mkdir()
    (data_root / "user_filters.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(loader_module, "get_user_data_dir", lambda: data_root)

    with pytest.raises(json.JSONDecodeError):
        FilterInventoryLoader.load()


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
