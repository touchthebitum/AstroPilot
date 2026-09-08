import copy
from types import MappingProxyType

import pytest

import astropilot.user_profile as user_profile
from astropilot.user_profile import (
    UserProfileError,
    create_or_replace_user_configuration,
    load_user_profile,
)


def minimal_candidate():
    return {
        "location": {
            "name": "La Chaux-de-Fonds",
            "latitude": 47.1035,
            "longitude": 6.8328,
        },
        "preferences": {"bortle": 4},
        "available_equipment": ["samyang_183"],
        "active_equipment": "samyang_183",
        "projects": {
            "M31": {
                "target_hours": 10,
            }
        },
    }


def custom_equipment_definition():
    return {
        "optics_manufacturer": "Askar",
        "optics_model": "FRA300",
        "focal_length_mm": 300,
        "aperture_mm": 60,
        "f_ratio": 5,
        "camera_manufacturer": "ZWO",
        "camera_model": "ASI533MM",
        "pixel_size_um": 3.76,
        "sensor_width_px": 3008,
        "sensor_height_px": 3008,
        "monochrome": True,
    }


def test_creates_normalized_reloadable_configuration_without_mutating_candidate(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "missing" / "user-data"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    original = copy.deepcopy(candidate)

    written = create_or_replace_user_configuration(
        MappingProxyType(candidate)
    )

    assert data_dir.is_dir()
    assert (data_dir / "user_profile.json").is_file()
    assert written == load_user_profile()
    assert written is not candidate
    assert written["sessions"] == []
    assert written["projects"]["M31"]["hours"] == 0
    assert candidate == original


def test_preserves_explicit_sessions_and_project_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    candidate = minimal_candidate()
    candidate["projects"]["M31"]["hours"] = 2
    candidate["sessions"] = [
        {
            "date": "2026-09-01",
            "object": "M31",
            "hours": 2,
        }
    ]

    written = create_or_replace_user_configuration(candidate)

    assert written["projects"]["M31"]["hours"] == 2
    assert written["sessions"] == candidate["sessions"]


def test_replaces_an_existing_valid_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    first = create_or_replace_user_configuration(minimal_candidate())
    replacement = minimal_candidate()
    replacement["location"]["name"] = "Mont Sujet"

    written = create_or_replace_user_configuration(replacement)

    assert written["location"]["name"] == "Mont Sujet"
    assert written != first
    assert load_user_profile() == written


@pytest.mark.parametrize(
    "mutate",
    [
        lambda candidate: candidate.pop("location"),
        lambda candidate: candidate.pop("preferences"),
        lambda candidate: candidate["preferences"].pop("bortle"),
        lambda candidate: candidate.pop("available_equipment"),
        lambda candidate: candidate.update(available_equipment=[]),
        lambda candidate: candidate.pop("projects"),
        lambda candidate: candidate["projects"]["M31"].pop("target_hours"),
    ],
)
def test_missing_v1_requirement_has_no_filesystem_effect(
    tmp_path,
    monkeypatch,
    mutate,
):
    data_dir = tmp_path / "missing" / "user-data"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    mutate(candidate)

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_empty_projects_mapping_is_persisted_and_reloadable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    candidate = minimal_candidate()
    candidate["projects"] = {}

    written = create_or_replace_user_configuration(candidate)

    assert written["projects"] == {}
    assert load_user_profile() == written


def test_projects_must_remain_a_mapping(tmp_path, monkeypatch):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["projects"] = []

    with pytest.raises(UserProfileError, match="projects"):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_invalid_bortle_is_rejected_by_historical_validator(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["preferences"]["bortle"] = 10
    calls = []
    historical_validator = user_profile.validate_user_profile

    def tracking_validator(profile, profile_path):
        calls.append(profile)
        return historical_validator(profile, profile_path)

    monkeypatch.setattr(
        user_profile,
        "validate_user_profile",
        tracking_validator,
    )

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert len(calls) == 1
    assert not data_dir.exists()


def test_unknown_equipment_is_rejected(tmp_path, monkeypatch):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["available_equipment"] = ["unknown_setup"]
    candidate["active_equipment"] = "unknown_setup"

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_custom_equipment_is_persisted_and_resolved_without_mutation(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    candidate = minimal_candidate()
    definition = custom_equipment_definition()
    candidate["equipment_definitions"] = {"custom_fra300": definition}
    candidate["available_equipment"] = ["custom_fra300"]
    candidate["active_equipment"] = "custom_fra300"
    original = copy.deepcopy(candidate)

    written = create_or_replace_user_configuration(candidate)
    loaded = load_user_profile()
    resolved = user_profile.resolve_equipment_definition(
        loaded,
        "custom_fra300",
    )

    assert written == loaded
    assert candidate == original
    assert "sensor_width_mm" not in loaded["equipment_definitions"]["custom_fra300"]
    assert "sensor_height_mm" not in loaded["equipment_definitions"]["custom_fra300"]
    assert resolved["sensor_width_mm"] == pytest.approx(11.31008)
    assert resolved["sensor_height_mm"] == pytest.approx(11.31008)


def test_preset_equipment_resolution_preserves_catalog_definition():
    assert user_profile.resolve_equipment_definition(
        {},
        "samyang_183",
    ) is user_profile.EQUIPMENT_PROFILES["samyang_183"]


@pytest.mark.parametrize(
    "field_name",
    [
        "optics_manufacturer",
        "optics_model",
        "focal_length_mm",
        "aperture_mm",
        "f_ratio",
        "camera_manufacturer",
        "camera_model",
        "pixel_size_um",
        "sensor_width_px",
        "sensor_height_px",
        "monochrome",
    ],
)
def test_custom_equipment_requires_every_foundation_field(
    tmp_path,
    monkeypatch,
    field_name,
):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    definition = custom_equipment_definition()
    definition.pop(field_name)
    candidate["equipment_definitions"] = {"custom_fra300": definition}
    candidate["available_equipment"] = ["custom_fra300"]
    candidate["active_equipment"] = "custom_fra300"

    with pytest.raises(UserProfileError, match=field_name):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("optics_manufacturer", ""),
        ("optics_model", " "),
        ("camera_manufacturer", None),
        ("camera_model", []),
        ("focal_length_mm", 0),
        ("aperture_mm", -1),
        ("f_ratio", float("inf")),
        ("pixel_size_um", True),
        ("sensor_width_px", 0),
        ("sensor_height_px", float("nan")),
        ("monochrome", 1),
    ],
)
def test_custom_equipment_rejects_invalid_foundation_values(
    tmp_path,
    monkeypatch,
    field_name,
    invalid_value,
):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    definition = custom_equipment_definition()
    definition[field_name] = invalid_value
    candidate["equipment_definitions"] = {"custom_fra300": definition}
    candidate["available_equipment"] = ["custom_fra300"]
    candidate["active_equipment"] = "custom_fra300"

    with pytest.raises(UserProfileError, match=field_name):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_active_equipment_must_be_available(tmp_path, monkeypatch):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["active_equipment"] = "fra400_2600"

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_unknown_project_is_rejected(tmp_path, monkeypatch):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["projects"] = {"UNKNOWN": {"target_hours": 10}}

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_catalog_project_without_coordinates_is_rejected(tmp_path, monkeypatch):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    monkeypatch.setitem(
        user_profile.CATALOG,
        "NO_COORDINATES",
        {"name": "Incomplete target"},
    )
    candidate = minimal_candidate()
    candidate["projects"] = {
        "NO_COORDINATES": {"target_hours": 10},
    }

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_legacy_setups_are_rejected_without_filesystem_effect(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["setups"] = {}

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_candidate_must_be_a_mapping(tmp_path, monkeypatch):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration([])

    assert not data_dir.exists()


def test_non_serializable_candidate_has_no_filesystem_effect(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["unsupported"] = object()

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()


def test_uncopyable_candidate_is_rejected_without_filesystem_effect(
    tmp_path,
    monkeypatch,
):
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise TypeError("cannot copy")

    data_dir = tmp_path / "missing"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(data_dir))
    candidate = minimal_candidate()
    candidate["unsupported"] = Uncopyable()

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(candidate)

    assert not data_dir.exists()
    assert not (data_dir / "user_profile.json").exists()
    assert not list(tmp_path.glob("missing/.user_profile.*.tmp"))


def test_invalid_candidate_preserves_existing_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    create_or_replace_user_configuration(minimal_candidate())
    profile_path = tmp_path / "user_profile.json"
    original = profile_path.read_bytes()
    invalid = minimal_candidate()
    invalid.pop("location")

    with pytest.raises(UserProfileError):
        create_or_replace_user_configuration(invalid)

    assert profile_path.read_bytes() == original


def test_replace_error_preserves_profile_and_cleans_temporary_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    create_or_replace_user_configuration(minimal_candidate())
    profile_path = tmp_path / "user_profile.json"
    original = profile_path.read_bytes()
    replacement = minimal_candidate()
    replacement["location"]["name"] = "Mont Sujet"

    def fail_replace(source, destination):
        raise PermissionError("replacement denied")

    monkeypatch.setattr(user_profile.os, "replace", fail_replace)

    with pytest.raises(PermissionError, match="replacement denied"):
        create_or_replace_user_configuration(replacement)

    assert profile_path.read_bytes() == original
    assert {path.name for path in tmp_path.iterdir()} == {
        "user_profile.json"
    }
