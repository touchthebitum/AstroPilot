import json

import pytest

import astropilot.user_profile as user_profile


def write_profile(path, *, project_hours=3.0, target_hours=20.0):
    profile = {
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