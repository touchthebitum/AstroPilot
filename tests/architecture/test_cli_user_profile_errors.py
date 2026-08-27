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


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("hours", "two"),
        ("hours", True),
        ("target_hours", -1),
        ("target_hours", float("inf")),
    ],
)
def test_invalid_project_hours_exit_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
    field_name,
    invalid_value,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "projects": {
                    "IC1396": {
                        field_name: invalid_value,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert f"projects['IC1396'].{field_name}" in captured.err
    assert "nombre fini positif ou nul" in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


@pytest.mark.parametrize(
    ("session", "field_name", "expected_type"),
    [
        ({"hours": 1}, "object", "chaîne non vide"),
        ({"object": 1396, "hours": 1}, "object", "chaîne non vide"),
        ({"object": "IC1396"}, "hours", "nombre fini strictement positif"),
        (
            {"object": "IC1396", "hours": "two"},
            "hours",
            "nombre fini strictement positif",
        ),
        (
            {"object": "IC1396", "hours": 0},
            "hours",
            "nombre fini strictement positif",
        ),
        (
            {"object": "IC1396", "hours": -1},
            "hours",
            "nombre fini strictement positif",
        ),
        (
            {"object": "IC1396", "hours": float("inf")},
            "hours",
            "nombre fini strictement positif",
        ),
        (
            {"object": "IC1396", "hours": 1, "filter_type": []},
            "filter_type",
            "chaîne non vide ou null",
        ),
        (
            {"object": "IC1396", "hours": 1, "filter_type": " "},
            "filter_type",
            "chaîne non vide ou null",
        ),
    ],
)
def test_invalid_session_fields_exit_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
    session,
    field_name,
    expected_type,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps({"sessions": [session]}),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert f"sessions[0].{field_name}" in captured.err
    assert expected_type in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


@pytest.mark.parametrize(
    ("project", "expected_location", "expected_message"),
    [
        (
            {"target_hours": 6, "filter_targets": []},
            "projects['IC1396'].filter_targets",
            "objet JSON",
        ),
        (
            {"target_hours": 6, "filter_targets": {"": 6}},
            "projects['IC1396'].filter_targets",
            "nom de filtre non vide",
        ),
        (
            {"target_hours": 6, "filter_targets": {"Ha": "six"}},
            "filter_targets['Ha']",
            "nombre fini positif ou nul",
        ),
        (
            {"target_hours": 6, "filter_targets": {"Ha": True}},
            "filter_targets['Ha']",
            "nombre fini positif ou nul",
        ),
        (
            {"target_hours": 6, "filter_targets": {"Ha": -1}},
            "filter_targets['Ha']",
            "nombre fini positif ou nul",
        ),
        (
            {"target_hours": 6, "filter_targets": {"Ha": float("inf")}},
            "filter_targets['Ha']",
            "nombre fini positif ou nul",
        ),
        (
            {"filter_targets": {"Ha": 6}},
            "projects['IC1396'].target_hours",
            "requis",
        ),
        (
            {"target_hours": 6, "filter_targets": {"Ha": 5}},
            "projects['IC1396'].filter_targets",
            "somme 5.00 h",
        ),
    ],
)
def test_invalid_filter_targets_exit_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
    project,
    expected_location,
    expected_message,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps({"projects": {"IC1396": project}}),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--filter-targets-show", "IC1396"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert expected_location in captured.err
    assert expected_message in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


def test_consistent_filter_targets_remain_valid(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "active_equipment": "samyang_183",
                "available_equipment": ["samyang_183"],
                "projects": {
                    "IC1396": {
                        "target_hours": 6,
                        "filter_targets": {"Ha": 6},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    result = astro_score.main(["--filter-targets-show", "IC1396"])
    captured = capsys.readouterr()

    assert result == 0
    assert "• Ha: 6.0 h" in captured.out
    assert captured.err == ""
    assert profile_path.read_bytes() == original_content


@pytest.mark.parametrize(
    ("profile", "expected_location", "expected_message"),
    [
        (
            {"available_equipment": ["samyang_183"]},
            "active_equipment",
            "chaîne non vide requise",
        ),
        (
            {
                "active_equipment": [],
                "available_equipment": ["samyang_183"],
            },
            "active_equipment",
            "chaîne non vide requise",
        ),
        (
            {
                "active_equipment": "samyang_183",
                "available_equipment": ["fra400_2600"],
            },
            "active_equipment",
            "doit figurer dans available_equipment",
        ),
        (
            {
                "active_equipment": "unknown_setup",
                "available_equipment": ["unknown_setup"],
            },
            "available_equipment[0]",
            "matériel inconnu",
        ),
    ],
)
def test_invalid_equipment_configuration_exits_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
    profile,
    expected_location,
    expected_message,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert expected_location in captured.err
    assert expected_message in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


def test_known_active_equipment_remains_valid(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "active_equipment": "samyang_183",
                "available_equipment": ["samyang_183"],
            }
        ),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    result = astro_score.main(["--object", "M31"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Setup actif : samyang_183" in captured.out
    assert "samyang_183" in captured.out
    assert captured.err == ""
    assert profile_path.read_bytes() == original_content

@pytest.mark.parametrize(
    ("location", "expected_location"),
    [
        (
            {
                "latitude": 46.7508,
                "longitude": 6.5495,
            },
            "location.name",
        ),
        (
            {
                "name": "",
                "latitude": 46.7508,
                "longitude": 6.5495,
            },
            "location.name",
        ),
        (
            {
                "name": "Buttes",
                "longitude": 6.5495,
            },
            "location.latitude",
        ),
        (
            {
                "name": "Buttes",
                "latitude": 46.7508,
            },
            "location.longitude",
        ),
        (
            {
                "name": "Buttes",
                "latitude": "46.7508",
                "longitude": 6.5495,
            },
            "location.latitude",
        ),
        (
            {
                "name": "Buttes",
                "latitude": 46.7508,
                "longitude": True,
            },
            "location.longitude",
        ),
        (
            {
                "name": "Buttes",
                "latitude": float("nan"),
                "longitude": 6.5495,
            },
            "location.latitude",
        ),
        (
            {
                "name": "Buttes",
                "latitude": 46.7508,
                "longitude": float("inf"),
            },
            "location.longitude",
        ),
        (
            {
                "name": "Buttes",
                "latitude": 91.0,
                "longitude": 6.5495,
            },
            "location.latitude",
        ),
        (
            {
                "name": "Buttes",
                "latitude": 46.7508,
                "longitude": 181.0,
            },
            "location.longitude",
        ),
    ],
)
def test_invalid_location_exits_cleanly(
    tmp_path,
    monkeypatch,
    capsys,
    location,
    expected_location,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "active_equipment": "samyang_183",
                "available_equipment": ["samyang_183"],
                "location": location,
            },
            allow_nan=True,
        ),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()

    monkeypatch.setenv(
        "ASTROPILOT_DATA_DIR",
        str(tmp_path),
    )

    with pytest.raises(SystemExit) as exit_info:
        astro_score.main(["--object", "M31"])

    captured = capsys.readouterr()

    assert exit_info.value.code == 2
    assert captured.out == ""
    assert expected_location in captured.err
    assert "Erreur profil utilisateur" in captured.err
    assert "Traceback" not in captured.err
    assert profile_path.read_bytes() == original_content


def test_valid_location_remains_accepted(
    tmp_path,
    monkeypatch,
    capsys,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "active_equipment": "samyang_183",
                "available_equipment": ["samyang_183"],
                "location": {
                    "name": "Buttes",
                    "latitude": 46.7508,
                    "longitude": 6.5495,
                },
            }
        ),
        encoding="utf-8",
    )
    original_content = profile_path.read_bytes()

    monkeypatch.setenv(
        "ASTROPILOT_DATA_DIR",
        str(tmp_path),
    )

    result = astro_score.main(["--object", "M31"])
    captured = capsys.readouterr()

    assert result == 0
    assert "Setup actif : samyang_183" in captured.out
    assert captured.err == ""
    assert profile_path.read_bytes() == original_content
