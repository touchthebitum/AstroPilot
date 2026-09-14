import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import contextmanager
from threading import Barrier
from types import SimpleNamespace

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


def test_user_data_dir_defaults_to_writable_per_user_path(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTROPILOT_DATA_DIR", raising=False)
    monkeypatch.setattr(
        user_profile,
        "_default_user_data_dir",
        lambda: tmp_path / "user-data",
    )

    assert user_profile.get_user_data_dir() == tmp_path / "user-data"


def test_default_user_data_dir_is_outside_package_data(monkeypatch):
    monkeypatch.delenv("ASTROPILOT_DATA_DIR", raising=False)

    default = user_profile.get_user_data_dir()

    assert default != user_profile.DATA_DIR
    if user_profile.sys.platform == "darwin":
        assert default == (
            user_profile.Path.home()
            / "Library"
            / "Application Support"
            / "AstroPilot"
        )
    elif user_profile.os.name == "nt":
        assert default.name == "AstroPilot"
    else:
        assert default.name == "astropilot"


def test_default_user_data_dir_supports_new_profile_write(tmp_path, monkeypatch):
    data_dir = tmp_path / "per-user" / "AstroPilot"
    monkeypatch.delenv("ASTROPILOT_DATA_DIR", raising=False)
    monkeypatch.setattr(
        user_profile,
        "_default_user_data_dir",
        lambda: data_dir,
    )

    saved = user_profile.save_user_profile(
        {
            "active_equipment": "samyang_183",
            "available_equipment": ["samyang_183"],
            "projects": {},
            "sessions": [],
        }
    )

    assert saved["profile_revision"] == 1
    assert (data_dir / "user_profile.json").is_file()
    assert not user_profile.DATA_DIR.is_relative_to(tmp_path)


def test_all_canonical_durable_stores_share_user_data_root(
    tmp_path,
    monkeypatch,
):
    import astro_score

    monkeypatch.setattr(astro_score, "get_user_data_dir", lambda: tmp_path)

    service = astro_score.build_durable_tonight_application_service()

    assert service.evidence_store._directory == (
        tmp_path / "decision_forecast_evidence"
    )
    assert service.acceptance_lineage_store._directory == (
        tmp_path / "decision_lineage"
    )
    assert service.execution_lineage_store._directory == (
        tmp_path / "execution_lineage"
    )


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

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

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

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

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

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

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

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

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

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

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

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

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

    assert replaced["source"].name.startswith(".user_profile.")
    assert replaced["source"].name.endswith(".tmp")
    assert replaced["target"].name == "user_profile.json"

def test_record_session_persists_filter_type_when_provided(
    tmp_path,
    monkeypatch,
):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)

    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

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


def test_portfolio_credit_ledger_requires_a_json_object(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    profile = json.loads(profile_path.read_text())
    profile["portfolio_credit_applications"] = []
    profile_path.write_text(json.dumps(profile))
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(user_profile.UserProfileError, match="portfolio_credit_applications"):
        user_profile.load_user_profile()


def test_legacy_profile_loads_at_revision_zero(tmp_path, monkeypatch):
    write_profile(tmp_path / "user_profile.json")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    assert user_profile.load_user_profile()["profile_revision"] == 0


@pytest.mark.parametrize("invalid_revision", [-1, 1.5, True, "1"])
def test_profile_revision_must_be_a_non_negative_integer(
    tmp_path,
    monkeypatch,
    invalid_revision,
):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["profile_revision"] = invalid_revision
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(user_profile.UserProfileError, match="profile_revision"):
        user_profile.load_user_profile()


def test_first_cas_write_increments_revision_once(tmp_path, monkeypatch):
    write_profile(tmp_path / "user_profile.json")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    profile = user_profile.load_user_profile()
    profile["projects"]["M31"]["hours"] = 4.0

    saved = user_profile.save_user_profile(profile, expected_revision=0)

    assert saved["profile_revision"] == 1
    assert user_profile.load_user_profile()["profile_revision"] == 1


def test_stale_cas_write_preserves_newer_document(tmp_path, monkeypatch):
    write_profile(tmp_path / "user_profile.json")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    first = user_profile.load_user_profile()
    stale = deepcopy(first)
    first["preferences"] = {"bortle": 4}
    user_profile.save_user_profile(first, expected_revision=0)
    before = (tmp_path / "user_profile.json").read_bytes()
    stale["projects"]["M31"]["hours"] = 9.0
    monkeypatch.setattr(
        user_profile.Path,
        "replace",
        lambda *args: pytest.fail("conflict must precede replacement"),
    )

    with pytest.raises(user_profile.ProfileRevisionConflictError):
        user_profile.save_user_profile(stale, expected_revision=0)

    assert (tmp_path / "user_profile.json").read_bytes() == before


def test_record_session_rejects_stale_loaded_profile(tmp_path, monkeypatch):
    write_profile(tmp_path / "user_profile.json")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    stale = deepcopy(user_profile.load_user_profile())
    newer = deepcopy(stale)
    newer["preferences"] = {"bortle": 4}
    user_profile.save_user_profile(newer, expected_revision=0)
    before = (tmp_path / "user_profile.json").read_bytes()
    monkeypatch.setattr(
        user_profile,
        "load_user_profile",
        lambda: deepcopy(stale),
    )

    with pytest.raises(user_profile.ProfileRevisionConflictError):
        user_profile.record_session(
            "M31",
            1.0,
            "2026-09-11",
        )

    assert (tmp_path / "user_profile.json").read_bytes() == before


def test_concurrent_cas_writers_allow_exactly_one_commit(tmp_path, monkeypatch):
    write_profile(tmp_path / "user_profile.json")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    snapshots = [deepcopy(user_profile.load_user_profile()) for _ in range(2)]
    snapshots[0]["projects"]["M31"]["hours"] = 4.0
    snapshots[1]["projects"]["M31"]["hours"] = 5.0
    barrier = Barrier(2)

    def save(snapshot):
        barrier.wait()
        try:
            user_profile.save_user_profile(snapshot, expected_revision=0)
            return "saved"
        except user_profile.ProfileRevisionConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(save, snapshots))

    persisted = user_profile.load_user_profile()
    assert sorted(outcomes) == ["conflict", "saved"]
    assert persisted["profile_revision"] == 1
    assert persisted["projects"]["M31"]["hours"] in {4.0, 5.0}


def test_cas_uses_unique_temporary_files_and_cleans_them(
    tmp_path,
    monkeypatch,
):
    write_profile(tmp_path / "user_profile.json")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    temporary_names = []
    original_replace = user_profile.Path.replace

    def record_replace(path, target):
        temporary_names.append(path.name)
        return original_replace(path, target)

    monkeypatch.setattr(user_profile.Path, "replace", record_replace)
    for hours in (4.0, 5.0):
        profile = user_profile.load_user_profile()
        revision = profile["profile_revision"]
        profile["projects"]["M31"]["hours"] = hours
        user_profile.save_user_profile(profile, expected_revision=revision)

    assert len(set(temporary_names)) == 2
    assert user_profile.load_user_profile()["profile_revision"] == 2
    assert not list(tmp_path.glob(".user_profile.*.tmp"))


def test_corrupt_profile_is_quarantined_byte_for_byte_without_touching_other_data(
    tmp_path,
    monkeypatch,
):
    corrupt_bytes = b'{"broken": "exact bytes" trailing}'
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_bytes(corrupt_bytes)
    sentinel = tmp_path / "decision_lineage" / "sentinel.json"
    sentinel.parent.mkdir()
    sentinel.write_bytes(b"lineage stays exact")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    result = user_profile.quarantine_corrupt_user_profile(
        validate_configuration=lambda profile: profile,
    )

    assert result == "quarantined"
    assert not profile_path.exists()
    quarantines = list(tmp_path.glob(".user_profile.corrupt.*.json"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == corrupt_bytes
    assert sentinel.read_bytes() == b"lineage stays exact"


def test_valid_profile_is_protected_from_corrupt_recovery(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.json"
    write_profile(profile_path)
    before = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    with pytest.raises(user_profile.ProfileRecoveryConflictError):
        user_profile.quarantine_corrupt_user_profile(
            validate_configuration=lambda profile: profile,
        )

    assert profile_path.read_bytes() == before
    assert not list(tmp_path.glob(".user_profile.corrupt.*.json"))


def test_profile_repaired_before_locked_revalidation_is_preserved(
    tmp_path,
    monkeypatch,
):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    original_lock = user_profile._profile_write_lock
    repaired = {}

    @contextmanager
    def repair_before_lock_yields(data_dir):
        with original_lock(data_dir):
            write_profile(profile_path)
            repaired["bytes"] = profile_path.read_bytes()
            yield

    monkeypatch.setattr(
        user_profile,
        "_profile_write_lock",
        repair_before_lock_yields,
    )

    with pytest.raises(user_profile.ProfileRecoveryConflictError):
        user_profile.quarantine_corrupt_user_profile(
            validate_configuration=lambda profile: profile,
        )

    assert profile_path.read_bytes() == repaired["bytes"]
    assert not list(tmp_path.glob(".user_profile.corrupt.*.json"))


def test_quarantine_collision_generates_another_name(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("{broken", encoding="utf-8")
    existing = tmp_path / ".user_profile.corrupt.collision.json"
    existing.write_bytes(b"existing quarantine")
    generated = iter(
        [SimpleNamespace(hex="collision"), SimpleNamespace(hex="fresh")]
    )
    monkeypatch.setattr(user_profile, "uuid4", lambda: next(generated))
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    result = user_profile.quarantine_corrupt_user_profile(
        validate_configuration=lambda profile: profile,
    )

    assert result == "quarantined"
    assert existing.read_bytes() == b"existing quarantine"
    assert (tmp_path / ".user_profile.corrupt.fresh.json").read_text(
        encoding="utf-8"
    ) == "{broken"


def test_quarantine_rename_failure_preserves_active_profile(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("{private broken content", encoding="utf-8")
    before = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        user_profile.Path,
        "rename",
        lambda *args: (_ for _ in ()).throw(OSError("private path detail")),
    )

    with pytest.raises(OSError, match="private path detail"):
        user_profile.quarantine_corrupt_user_profile(
            validate_configuration=lambda profile: profile,
        )

    assert profile_path.read_bytes() == before
    assert not list(tmp_path.glob(".user_profile.corrupt.*.json"))


def test_recovery_lock_failure_preserves_active_profile(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("{broken", encoding="utf-8")
    before = profile_path.read_bytes()
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))

    @contextmanager
    def unavailable_lock(data_dir):
        del data_dir
        raise OSError("private lock detail")
        yield

    monkeypatch.setattr(
        user_profile,
        "_profile_write_lock",
        unavailable_lock,
    )

    with pytest.raises(OSError, match="private lock detail"):
        user_profile.quarantine_corrupt_user_profile(
            validate_configuration=lambda profile: profile,
        )

    assert profile_path.read_bytes() == before
    assert not list(tmp_path.glob(".user_profile.corrupt.*.json"))
