import json

import pytest

import astropilot.user_profile as user_profile


def write_profile(path, *, project_hours=3.0, target_hours=20.0):
    profile = {
        "active_equipment": "samyang_183",
        "available_equipment": ["samyang_183"],
        "projects": {
            "M31": {
                "hours": project_hours,
                "target_hours": target_hours,
                "importance": 8,
            }
        },
        "sessions": [],
    }

    path.write_text(
        json.dumps(profile),
        encoding="utf-8",
    )


def test_user_data_dir_environment_overrides_legacy_path(
    tmp_path,
    monkeypatch,
):
    configured_dir = tmp_path / "configured"
    configured_dir.mkdir()
    write_profile(configured_dir / "user_profile.json")

    monkeypatch.setenv(
        "ASTROPILOT_DATA_DIR",
        str(configured_dir),
    )
    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path / "legacy",
    )

    assert user_profile.get_user_data_dir() == configured_dir
    assert user_profile.load_user_profile()["projects"]["M31"][
        "hours"
    ] == 3.0


def test_user_data_dir_defaults_to_legacy_path(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTROPILOT_DATA_DIR", raising=False)
    monkeypatch.setattr(user_profile, "DATA_DIR", tmp_path)

    assert user_profile.get_user_data_dir() == tmp_path


@pytest.mark.parametrize(
    ("preferences", "expected_altitude"),
    [
        ({}, 30),
        ({"min_altitude_deg": 25}, 25),
        ({"minimum_altitude_deg": 35}, 35),
        (
            {
                "min_altitude_deg": 40,
                "minimum_altitude_deg": 40,
            },
            40,
        ),
    ],
)
def test_minimum_altitude_preference_aliases(
    preferences,
    expected_altitude,
):
    assert (
        user_profile.resolve_minimum_altitude_deg(preferences)
        == expected_altitude
    )


def test_save_user_profile_uses_configured_data_dir(
    tmp_path,
    monkeypatch,
):
    configured_dir = tmp_path / "configured"
    legacy_dir = tmp_path / "legacy"
    configured_dir.mkdir()
    legacy_dir.mkdir()
    write_profile(configured_dir / "user_profile.json")
    write_profile(
        legacy_dir / "user_profile.json",
        project_hours=9.0,
    )

    monkeypatch.setenv(
        "ASTROPILOT_DATA_DIR",
        str(configured_dir),
    )
    monkeypatch.setattr(user_profile, "DATA_DIR", legacy_dir)

    profile = user_profile.load_user_profile()
    profile["projects"]["M31"]["hours"] = 4.5
    user_profile.save_user_profile(profile)

    assert user_profile.load_user_profile()["projects"]["M31"][
        "hours"
    ] == 4.5
    assert json.loads(
        (legacy_dir / "user_profile.json").read_text(
            encoding="utf-8"
        )
    )["projects"]["M31"]["hours"] == 9.0


def test_record_session_updates_project_and_history(
    tmp_path,
    monkeypatch,
):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)

    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path,
    )

    user_profile.record_session(
        "M31",
        2.5,
        "2026-08-16",
    )

    profile = user_profile.load_user_profile()

    assert profile["projects"]["M31"]["hours"] == 5.5
    assert profile["sessions"] == [
        {
            "date": "2026-08-16",
            "object": "M31",
            "hours": 2.5,
        }
    ]


def test_record_session_caps_hours_at_project_target(
    tmp_path,
    monkeypatch,
):
    profile_path = tmp_path / "user_profile.json"
    write_profile(
        profile_path,
        project_hours=19.0,
        target_hours=20.0,
    )

    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path,
    )

    user_profile.record_session(
        "M31",
        3.0,
        "2026-08-16",
    )

    profile = user_profile.load_user_profile()

    assert profile["projects"]["M31"]["hours"] == 20.0


def test_record_session_rejects_unknown_project(
    tmp_path,
    monkeypatch,
):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)

    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path,
    )

    with pytest.raises(ValueError):
        user_profile.record_session(
            "UNKNOWN",
            1.0,
            "2026-08-16",
        )


def test_record_session_rejects_non_positive_hours(
    tmp_path,
    monkeypatch,
):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)

    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path,
    )

    with pytest.raises(ValueError):
        user_profile.record_session(
            "M31",
            0,
            "2026-08-16",
        )

def test_save_user_profile_replaces_file_atomically(
    tmp_path,
    monkeypatch,
):
    write_profile(
        tmp_path / "user_profile.json"
    )

    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path,
    )

    profile = user_profile.load_user_profile()
    profile["projects"]["M31"]["hours"] = 7.5

    user_profile.save_user_profile(profile)

    saved = user_profile.load_user_profile()

    assert saved["projects"]["M31"]["hours"] == 7.5
    assert not (
        tmp_path / "user_profile.json.tmp"
    ).exists()


def test_save_user_profile_uses_atomic_replace(
    tmp_path,
    monkeypatch,
):
    write_profile(
        tmp_path / "user_profile.json"
    )

    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path,
    )

    replaced = {}

    original_replace = user_profile.Path.replace


    def tracking_replace(path, target):
        replaced["source"] = path
        replaced["target"] = target
        return original_replace(path, target)

    monkeypatch.setattr(
        user_profile.Path,
        "replace",
        tracking_replace,
    )

    profile = user_profile.load_user_profile()
    profile["projects"]["M31"]["hours"] = 8.0

    user_profile.save_user_profile(profile)

    assert replaced["source"].name == "user_profile.json.tmp"
    assert replaced["target"].name == "user_profile.json"

def test_record_session_persists_filter_type_when_provided(
    tmp_path,
    monkeypatch,
):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)

    monkeypatch.setattr(
        user_profile,
        "DATA_DIR",
        tmp_path,
    )

    user_profile.record_session(
        "M31",
        2.0,
        "2026-08-16",
        filter_type="LRGB",
    )

    profile = user_profile.load_user_profile()

    assert profile["sessions"] == [
        {
            "date": "2026-08-16",
            "object": "M31",
            "hours": 2.0,
            "filter_type": "LRGB",
        }
    ]
