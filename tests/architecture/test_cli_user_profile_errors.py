import json

import pytest

import astro_score


def test_missing_user_profile_exits_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile_path = tmp_path / "user_profile.json"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert "Profil utilisateur introuvable" in captured.err
    assert str(profile_path) in captured.err
    assert "ASTROPILOT_DATA_DIR" in captured.err
    assert "Traceback" not in captured.err
    assert not profile_path.exists()


def test_invalid_user_profile_exits_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        '{"active_equipment": "samyang_183",',
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert "JSON invalide" in captured.err
    assert str(profile_path) in captured.err
    assert "ligne 1" in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


def test_non_object_user_profile_exits_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("[]", encoding="utf-8")
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert "racine" in captured.err
    assert "objet JSON attendu" in captured.err
    assert str(profile_path) in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "expected_type"),
    [
        ("available_equipment", {}, "liste"),
        ("preferences", [], "objet JSON"),
        ("projects", [], "objet JSON"),
        ("sessions", {}, "liste"),
        ("location", [], "objet JSON"),
        ("decision_weights", [], "objet JSON"),
    ],
)
def test_invalid_profile_container_exits_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
    field_name,
    invalid_value,
    expected_type,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps({field_name: invalid_value}),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert field_name in captured.err
    assert expected_type in captured.err
    assert str(profile_path) in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


@pytest.mark.parametrize(
    ("profile", "expected_location", "expected_type"),
    [
        (
            {"available_equipment": [123]},
            "available_equipment[0]",
            "chaîne non vide",
        ),
        (
            {"available_equipment": [" "]},
            "available_equipment[0]",
            "chaîne non vide",
        ),
        (
            {"projects": {"IC1396": []}},
            "projects['IC1396']",
            "objet JSON",
        ),
        (
            {"sessions": ["invalid session"]},
            "sessions[0]",
            "objet JSON",
        ),
    ],
)
def test_invalid_profile_entry_exits_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
    profile,
    expected_location,
    expected_type,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps(profile),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert expected_location in captured.err
    assert expected_type in captured.err
    assert str(profile_path) in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content
