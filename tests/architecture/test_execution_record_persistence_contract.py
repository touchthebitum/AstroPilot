import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from astropilot.execution_record_store import FileExecutionRecordStore
from astropilot.user_profile import get_user_data_dir
from decision.execution_record import ExecutionRecord
from decision.execution_record_persistence import (
    ExecutionRecordPersistenceError,
    deserialize_execution_record,
    serialize_execution_record,
)


START = datetime(2026, 9, 1, 20, 15, 30, 123456, tzinfo=timezone.utc)


def execution(**overrides):
    values = {
        "execution_id": "execution-123",
        "decision_id": None,
        "started_at_utc": START,
        "ended_at_utc": START + timedelta(hours=2),
        "object": "M31",
        "hours": 1.5,
        "filter_type": None,
    }
    values.update(overrides)
    return ExecutionRecord(**values)


def document_for(source=None):
    return serialize_execution_record(source or execution())


def test_execution_document_is_canonical_strict_and_lossless():
    source = execution()
    document = document_for(source)
    restored = deserialize_execution_record(
        document,
        execution_id=source.execution_id,
    )
    payload = json.loads(document)

    assert restored == source
    assert document == document_for(source)
    assert set(payload) == {"schema_version", "execution"}
    assert payload["schema_version"] == 1
    assert set(payload["execution"]) == {
        "execution_id",
        "decision_id",
        "started_at_utc",
        "ended_at_utc",
        "object",
        "hours",
        "filter_type",
    }
    assert payload["execution"]["started_at_utc"].endswith("+00:00")
    assert payload["execution"]["ended_at_utc"].endswith("+00:00")
    assert payload["execution"]["decision_id"] is None
    assert payload["execution"]["filter_type"] is None


@pytest.mark.parametrize("level", ["root", "execution"])
def test_unknown_fields_are_rejected(level):
    payload = json.loads(document_for())
    target = payload if level == "root" else payload["execution"]
    target["unexpected"] = True

    with pytest.raises(ExecutionRecordPersistenceError):
        deserialize_execution_record(
            json.dumps(payload),
            execution_id="execution-123",
        )


@pytest.mark.parametrize("field", ["schema_version", "execution"])
def test_missing_root_fields_are_rejected(field):
    payload = json.loads(document_for())
    del payload[field]

    with pytest.raises(ExecutionRecordPersistenceError):
        deserialize_execution_record(
            json.dumps(payload),
            execution_id="execution-123",
        )


def test_missing_execution_field_is_rejected():
    payload = json.loads(document_for())
    del payload["execution"]["filter_type"]

    with pytest.raises(ExecutionRecordPersistenceError):
        deserialize_execution_record(
            json.dumps(payload),
            execution_id="execution-123",
        )


@pytest.mark.parametrize("version", [2, "1", True, None])
def test_invalid_schema_version_is_rejected(version):
    payload = json.loads(document_for())
    payload["schema_version"] = version

    with pytest.raises(
        ExecutionRecordPersistenceError,
        match="invalid_schema_version",
    ):
        deserialize_execution_record(
            json.dumps(payload),
            execution_id="execution-123",
        )


@pytest.mark.parametrize(
    "document",
    [
        "{",
        "[]",
        "null",
        '{"hours": NaN}',
        '{"hours": Infinity}',
        '{"hours": -Infinity}',
    ],
)
def test_invalid_or_non_finite_json_is_rejected(document):
    with pytest.raises(ExecutionRecordPersistenceError):
        deserialize_execution_record(document, execution_id="execution-123")


def test_execution_identity_mismatch_is_rejected():
    with pytest.raises(
        ExecutionRecordPersistenceError,
        match="execution_id_mismatch",
    ):
        deserialize_execution_record(
            document_for(),
            execution_id="execution-other",
        )


def test_missing_store_entry_returns_none(tmp_path):
    store = FileExecutionRecordStore(tmp_path)

    assert store.load(execution_id="missing-execution") is None


def test_store_supports_the_canonical_user_data_root(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    directory = get_user_data_dir() / "execution_records"
    store = FileExecutionRecordStore(directory)

    store.save(execution=execution())

    assert (directory / "execution-123.json").is_file()
    assert not (tmp_path / "user_profile.json").exists()


def test_store_round_trip_and_identical_save_are_idempotent(tmp_path):
    store = FileExecutionRecordStore(tmp_path)
    source = execution()

    store.save(execution=source)
    initial = (tmp_path / "execution-123.json").read_bytes()
    store.save(execution=source)

    assert store.load(execution_id="execution-123") == source
    assert (tmp_path / "execution-123.json").read_bytes() == initial


def test_store_rejects_conflicting_execution(tmp_path):
    store = FileExecutionRecordStore(tmp_path)
    source = execution()
    store.save(execution=source)

    with pytest.raises(
        ExecutionRecordPersistenceError,
        match="execution_record_conflict",
    ):
        store.save(execution=execution(hours=1.75))

    assert store.load(execution_id="execution-123") == source


def test_present_corrupt_file_raises_explicit_error(tmp_path):
    (tmp_path / "execution-123.json").write_text("{", encoding="utf-8")
    store = FileExecutionRecordStore(tmp_path)

    with pytest.raises(ExecutionRecordPersistenceError):
        store.load(execution_id="execution-123")


def test_store_atomically_publishes_a_complete_temp_file(tmp_path, monkeypatch):
    store = FileExecutionRecordStore(tmp_path)
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
    store.save(execution=execution())

    assert len(publications) == 1
    parent, destination, complete_document = publications[0]
    assert parent == tmp_path
    assert destination == tmp_path / "execution-123.json"
    assert json.loads(complete_document)["execution"]["execution_id"] == (
        "execution-123"
    )


def test_concurrent_different_record_is_never_overwritten(tmp_path, monkeypatch):
    store = FileExecutionRecordStore(tmp_path)
    concurrent = execution(hours=1.75)
    real_link = os.link

    def publish_competitor_then_link(source, destination):
        concurrent_temp = tmp_path / "concurrent.tmp"
        concurrent_temp.write_text(document_for(concurrent), encoding="utf-8")
        real_link(concurrent_temp, destination)
        concurrent_temp.unlink()
        real_link(source, destination)

    monkeypatch.setattr(os, "link", publish_competitor_then_link)

    with pytest.raises(
        ExecutionRecordPersistenceError,
        match="execution_record_conflict",
    ):
        store.save(execution=execution())

    assert store.load(execution_id="execution-123") == concurrent


def test_concurrent_identical_record_is_idempotent(tmp_path, monkeypatch):
    store = FileExecutionRecordStore(tmp_path)
    source_record = execution()
    real_link = os.link

    def publish_identical_then_link(source, destination):
        concurrent_temp = tmp_path / "concurrent.tmp"
        concurrent_temp.write_text(document_for(source_record), encoding="utf-8")
        real_link(concurrent_temp, destination)
        concurrent_temp.unlink()
        real_link(source, destination)

    monkeypatch.setattr(os, "link", publish_identical_then_link)

    store.save(execution=source_record)

    assert store.load(execution_id="execution-123") == source_record


def test_store_cleans_temporary_file_when_publication_fails(
    tmp_path,
    monkeypatch,
):
    store = FileExecutionRecordStore(tmp_path)

    def fail_link(source, destination):
        raise OSError("publication failed")

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(OSError, match="publication failed"):
        store.save(execution=execution())

    assert list(tmp_path.iterdir()) == []


def test_cleanup_failure_does_not_mask_publication_failure(
    tmp_path,
    monkeypatch,
):
    store = FileExecutionRecordStore(tmp_path)

    def fail_link(source, destination):
        raise OSError("primary publication failure")

    def fail_unlink(self, missing_ok=False):
        raise PermissionError("secondary cleanup failure")

    monkeypatch.setattr(os, "link", fail_link)
    monkeypatch.setattr(type(tmp_path), "unlink", fail_unlink)

    with pytest.raises(OSError, match="primary publication failure"):
        store.save(execution=execution())


def test_cleanup_failure_after_successful_publication_is_not_silenced(
    tmp_path,
    monkeypatch,
):
    store = FileExecutionRecordStore(tmp_path)

    def fail_unlink(self, missing_ok=False):
        raise PermissionError("cleanup failure")

    monkeypatch.setattr(type(tmp_path), "unlink", fail_unlink)

    with pytest.raises(PermissionError, match="cleanup failure"):
        store.save(execution=execution())

    assert store.load(execution_id="execution-123") == execution()
