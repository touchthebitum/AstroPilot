import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from astropilot.field_observation_store import FileFieldObservationStore
from astropilot.user_profile import get_user_data_dir
from decision.field_observation import (
    CloudCondition,
    FieldObservation,
    SeeingCondition,
    Transparency,
)
from decision.field_observation_persistence import (
    FieldObservationPersistenceError,
    deserialize_field_observation,
    serialize_field_observation,
)


OBSERVED_AT = datetime(
    2026,
    9,
    1,
    21,
    17,
    30,
    123456,
    tzinfo=timezone.utc,
)


def observation(**overrides):
    values = {
        "observation_id": "observation-123",
        "execution_id": "execution-123",
        "observed_at_utc": OBSERVED_AT,
        "cloud_condition": CloudCondition.FEW,
        "transparency": Transparency.GOOD,
        "seeing": SeeingCondition.FAIR,
        "dew_detected": False,
    }
    values.update(overrides)
    return FieldObservation(**values)


def document_for(source=None):
    return serialize_field_observation(source or observation())


def test_document_round_trip_is_lossless_deterministic_and_strict():
    source = observation()
    document = document_for(source)
    restored = deserialize_field_observation(
        document,
        observation_id=source.observation_id,
    )
    payload = json.loads(document)

    assert restored == source
    assert document == document_for(source)
    assert set(payload) == {"schema_version", "observation"}
    assert payload["schema_version"] == 1
    assert set(payload["observation"]) == {
        "observation_id",
        "execution_id",
        "observed_at_utc",
        "cloud_condition",
        "transparency",
        "seeing",
        "dew_detected",
    }
    assert payload["observation"]["observed_at_utc"].endswith("+00:00")


def test_null_values_are_preserved_in_json_and_round_trip():
    source = observation(
        cloud_condition=CloudCondition.CLEAR,
        transparency=None,
        seeing=None,
        dew_detected=None,
    )
    payload = json.loads(document_for(source))["observation"]

    assert payload["transparency"] is None
    assert payload["seeing"] is None
    assert payload["dew_detected"] is None
    assert deserialize_field_observation(
        document_for(source),
        observation_id=source.observation_id,
    ) == source


@pytest.mark.parametrize("version", [2, "1", True, None])
def test_invalid_schema_version_is_rejected(version):
    payload = json.loads(document_for())
    payload["schema_version"] = version

    with pytest.raises(
        FieldObservationPersistenceError,
        match="invalid_schema_version",
    ):
        deserialize_field_observation(
            json.dumps(payload),
            observation_id="observation-123",
        )


@pytest.mark.parametrize("level", ["root", "observation"])
def test_unknown_fields_are_rejected(level):
    payload = json.loads(document_for())
    target = payload if level == "root" else payload["observation"]
    target["unexpected"] = True

    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(
            json.dumps(payload),
            observation_id="observation-123",
        )


@pytest.mark.parametrize(
    ("level", "field"),
    [
        ("root", "schema_version"),
        ("root", "observation"),
        ("observation", "observation_id"),
        ("observation", "execution_id"),
        ("observation", "observed_at_utc"),
        ("observation", "cloud_condition"),
        ("observation", "transparency"),
        ("observation", "seeing"),
        ("observation", "dew_detected"),
    ],
)
def test_missing_required_fields_are_rejected(level, field):
    payload = json.loads(document_for())
    target = payload if level == "root" else payload["observation"]
    del target[field]

    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(
            json.dumps(payload),
            observation_id="observation-123",
        )

@pytest.mark.parametrize(
    ("field", "unknown"),
    [
        ("cloud_condition", "scattered"),
        ("transparency", "perfect"),
        ("seeing", "bad"),
    ],
)
def test_unknown_enum_values_are_rejected(field, unknown):
    payload = json.loads(document_for())
    payload["observation"][field] = unknown

    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(
            json.dumps(payload),
            observation_id="observation-123",
        )


@pytest.mark.parametrize("invalid", [0, True, [], {}])
def test_enum_fields_reject_non_string_json_types(invalid):
    payload = json.loads(document_for())
    payload["observation"]["cloud_condition"] = invalid

    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(
            json.dumps(payload),
            observation_id="observation-123",
        )


@pytest.mark.parametrize("invalid", [0, 1, "false", [], {}])
def test_dew_detected_rejects_non_boolean_json_types(invalid):
    payload = json.loads(document_for())
    payload["observation"]["dew_detected"] = invalid

    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(
            json.dumps(payload),
            observation_id="observation-123",
        )


@pytest.mark.parametrize(
    "document",
    [
        "{",
        "[]",
        "null",
        '{"value": NaN}',
        '{"value": Infinity}',
        '{"value": -Infinity}',
    ],
)
def test_invalid_or_non_standard_json_documents_are_rejected(document):
    with pytest.raises(FieldObservationPersistenceError):
        deserialize_field_observation(
            document,
            observation_id="observation-123",
        )


def test_document_identity_must_match_requested_identity():
    with pytest.raises(
        FieldObservationPersistenceError,
        match="observation_id_mismatch",
    ):
        deserialize_field_observation(
            document_for(),
            observation_id="observation-other",
        )


def test_missing_store_entry_returns_none(tmp_path):
    store = FileFieldObservationStore(tmp_path)

    assert store.load(observation_id="missing-observation") is None


def test_default_store_uses_canonical_user_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    store = FileFieldObservationStore()

    store.save(observation=observation())

    expected = (
        get_user_data_dir()
        / "field_observations"
        / "observation-123.json"
    )
    assert expected.is_file()
    assert not (tmp_path / "user_profile.json").exists()


def test_store_round_trip_and_identical_save_are_idempotent(tmp_path):
    store = FileFieldObservationStore(tmp_path)
    source = observation()

    store.save(observation=source)
    initial = (tmp_path / "observation-123.json").read_bytes()
    store.save(observation=source)

    assert store.load(observation_id="observation-123") == source
    assert (tmp_path / "observation-123.json").read_bytes() == initial


def test_store_rejects_sequential_conflict_without_overwrite(tmp_path):
    store = FileFieldObservationStore(tmp_path)
    source = observation()
    store.save(observation=source)

    with pytest.raises(
        FieldObservationPersistenceError,
        match="field_observation_conflict",
    ):
        store.save(
            observation=observation(cloud_condition=CloudCondition.OVERCAST)
        )

    assert store.load(observation_id="observation-123") == source


def test_present_corrupt_file_raises_explicit_error(tmp_path):
    (tmp_path / "observation-123.json").write_text("{", encoding="utf-8")
    store = FileFieldObservationStore(tmp_path)

    with pytest.raises(FieldObservationPersistenceError):
        store.load(observation_id="observation-123")


def test_store_atomically_publishes_complete_temp_file(tmp_path, monkeypatch):
    store = FileFieldObservationStore(tmp_path)
    publications = []
    real_link = os.link

    def inspect_then_link(source, destination):
        source_path = type(tmp_path)(source)
        destination_path = type(tmp_path)(destination)
        publications.append(
            (source_path.parent, destination_path, source_path.read_text())
        )
        real_link(source, destination)

    monkeypatch.setattr(os, "link", inspect_then_link)
    store.save(observation=observation())

    assert len(publications) == 1
    parent, destination, complete_document = publications[0]
    assert parent == tmp_path
    assert destination == tmp_path / "observation-123.json"
    assert json.loads(complete_document)["observation"]["observation_id"] == (
        "observation-123"
    )


def test_concurrent_different_observation_is_never_overwritten(
    tmp_path,
    monkeypatch,
):
    store = FileFieldObservationStore(tmp_path)
    concurrent = observation(cloud_condition=CloudCondition.OVERCAST)
    real_link = os.link

    def publish_competitor_then_link(source, destination):
        concurrent_temp = tmp_path / "concurrent.tmp"
        concurrent_temp.write_text(document_for(concurrent), encoding="utf-8")
        real_link(concurrent_temp, destination)
        concurrent_temp.unlink()
        real_link(source, destination)

    monkeypatch.setattr(os, "link", publish_competitor_then_link)

    with pytest.raises(
        FieldObservationPersistenceError,
        match="field_observation_conflict",
    ):
        store.save(observation=observation())

    assert store.load(observation_id="observation-123") == concurrent


def test_concurrent_identical_observation_is_idempotent(tmp_path, monkeypatch):
    store = FileFieldObservationStore(tmp_path)
    source_observation = observation()
    real_link = os.link

    def publish_identical_then_link(source, destination):
        concurrent_temp = tmp_path / "concurrent.tmp"
        concurrent_temp.write_text(
            document_for(source_observation),
            encoding="utf-8",
        )
        real_link(concurrent_temp, destination)
        concurrent_temp.unlink()
        real_link(source, destination)

    monkeypatch.setattr(os, "link", publish_identical_then_link)

    store.save(observation=source_observation)

    assert store.load(observation_id="observation-123") == source_observation


def test_store_cleans_temporary_file_when_publication_fails(
    tmp_path,
    monkeypatch,
):
    store = FileFieldObservationStore(tmp_path)

    def fail_link(source, destination):
        raise OSError("publication failed")

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(OSError, match="publication failed"):
        store.save(observation=observation())

    assert list(tmp_path.iterdir()) == []


def test_cleanup_failure_does_not_mask_publication_failure(
    tmp_path,
    monkeypatch,
):
    store = FileFieldObservationStore(tmp_path)

    def fail_link(source, destination):
        raise OSError("primary publication failure")

    def fail_unlink(self, missing_ok=False):
        raise PermissionError("secondary cleanup failure")

    monkeypatch.setattr(os, "link", fail_link)
    monkeypatch.setattr(type(tmp_path), "unlink", fail_unlink)

    with pytest.raises(OSError, match="primary publication failure"):
        store.save(observation=observation())


def test_cleanup_failure_after_successful_publication_is_not_silenced(
    tmp_path,
    monkeypatch,
):
    store = FileFieldObservationStore(tmp_path)

    def fail_unlink(self, missing_ok=False):
        raise PermissionError("cleanup failure")

    monkeypatch.setattr(type(tmp_path), "unlink", fail_unlink)

    with pytest.raises(PermissionError, match="cleanup failure"):
        store.save(observation=observation())

    assert store.load(observation_id="observation-123") == observation()
