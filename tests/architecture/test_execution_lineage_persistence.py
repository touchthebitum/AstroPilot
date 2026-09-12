import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

import astropilot.execution_lineage_store as store_module
from astropilot.execution_lineage_store import FileExecutionLineageStore
from decision.execution_lineage_persistence import (
    ExecutionLineageConflictError,
    ExecutionLineageCorruptionError,
    ExecutionLineageNotFoundError,
    ExecutionLineageStaleStateError,
    deserialize_execution,
    deserialize_outcome_evidence,
    serialize_execution,
    serialize_outcome_evidence,
)
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    FieldOutcomeEvidence,
    ImageOutcomeEvidence,
    OutcomeEvidenceCategory,
    OutcomeEvidenceSource,
    TechnicalOutcomeEvidence,
)


START = datetime(2026, 9, 12, 20, 30, tzinfo=timezone.utc)
END = datetime(2026, 9, 12, 22, 12, tzinfo=timezone.utc)
DURATION = END - START
OBSERVED_AT = END + timedelta(minutes=5)


def execution(status=ExecutionStatus.NOT_STARTED, *, execution_id="execution-1", mission_id="mission-1"):
    timing = {
        ExecutionStatus.NOT_STARTED: (None, None, None),
        ExecutionStatus.IN_PROGRESS: (START, None, None),
        ExecutionStatus.COMPLETED: (START, END, DURATION),
        ExecutionStatus.INTERRUPTED: (START, END, DURATION),
        ExecutionStatus.UNCONFIRMED: (None, None, None),
    }[status]
    return Execution(execution_id, mission_id, status, *timing)


def evidence(kind=AcquisitionOutcomeEvidence, *, evidence_id="evidence-1", execution_id="execution-1"):
    categories = {
        FieldOutcomeEvidence: OutcomeEvidenceCategory.FIELD,
        TechnicalOutcomeEvidence: OutcomeEvidenceCategory.TECHNICAL,
        AcquisitionOutcomeEvidence: OutcomeEvidenceCategory.ACQUISITION,
        ImageOutcomeEvidence: OutcomeEvidenceCategory.IMAGE,
    }
    values = {
        "evidence_id": evidence_id,
        "execution_id": execution_id,
        "category": categories[kind],
        "observed_at": OBSERVED_AT,
        "source": OutcomeEvidenceSource.USER,
    }
    if kind is AcquisitionOutcomeEvidence:
        values.update(
            actual_capture_duration=timedelta(hours=2, minutes=45),
            usable_integration_duration=timedelta(hours=1, minutes=12),
        )
    return kind(**values)


@pytest.mark.parametrize("status", tuple(ExecutionStatus))
def test_execution_round_trip_preserves_exact_types(status):
    source = execution(status)

    restored = deserialize_execution(serialize_execution(source))

    assert restored == source
    assert type(restored) is Execution
    assert type(restored.status) is ExecutionStatus
    if restored.actual_start is not None:
        assert type(restored.actual_start) is datetime
    if restored.actual_duration is not None:
        assert type(restored.actual_duration) is timedelta


@pytest.mark.parametrize(
    "kind",
    (
        FieldOutcomeEvidence,
        TechnicalOutcomeEvidence,
        AcquisitionOutcomeEvidence,
        ImageOutcomeEvidence,
    ),
)
def test_outcome_evidence_round_trip_preserves_concrete_subtype(kind):
    source = evidence(kind)

    restored = deserialize_outcome_evidence(serialize_outcome_evidence(source))

    assert restored == source
    assert type(restored) is kind
    assert type(restored.category) is OutcomeEvidenceCategory
    assert type(restored.observed_at) is datetime
    if kind is AcquisitionOutcomeEvidence:
        assert restored.actual_capture_duration == timedelta(hours=2, minutes=45)
        assert restored.usable_integration_duration == timedelta(hours=1, minutes=12)
        assert restored.actual_capture_duration != restored.usable_integration_duration


@pytest.mark.parametrize(
    "mutate",
    (
        lambda document: document["fields"].pop("mission_id"),
        lambda document: document["fields"].update(extra="unexpected"),
        lambda document: document["fields"]["status"].update(value="invalid"),
        lambda document: document["fields"]["actual_start"].update(value="invalid"),
        lambda document: document["fields"].update(
            actual_duration={
                "$type": "timedelta",
                "microseconds": float("inf"),
            }
        ),
    ),
)
def test_malformed_execution_representation_fails_closed(mutate):
    document = serialize_execution(execution(ExecutionStatus.IN_PROGRESS))
    mutate(document)

    with pytest.raises(ExecutionLineageCorruptionError):
        deserialize_execution(document)


def test_malformed_evidence_subtype_category_combination_fails_closed():
    document = serialize_outcome_evidence(evidence(FieldOutcomeEvidence))
    document["fields"]["category"]["value"] = "image"

    with pytest.raises(ExecutionLineageCorruptionError):
        deserialize_outcome_evidence(document)


def test_create_and_reload_execution_after_store_reconstruction(tmp_path):
    FileExecutionLineageStore(tmp_path).create_execution(execution())

    restored = FileExecutionLineageStore(tmp_path).load_execution("execution-1")

    assert restored == execution()
    assert type(restored) is Execution


def test_identical_creation_replay_is_idempotent(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    source = execution()

    assert store.create_execution(source) == source
    assert store.create_execution(source) == source


def test_new_execution_must_be_not_started(tmp_path):
    with pytest.raises(
        ExecutionLineageCorruptionError,
        match="execution_initial_state_invalid",
    ):
        FileExecutionLineageStore(tmp_path).create_execution(
            execution(ExecutionStatus.IN_PROGRESS)
        )


@pytest.mark.parametrize(
    "conflict",
    (
        execution(ExecutionStatus.IN_PROGRESS),
        execution(mission_id="mission-2"),
    ),
)
def test_conflicting_execution_identity_or_initial_content_fails(tmp_path, conflict):
    store = FileExecutionLineageStore(tmp_path)
    store.create_execution(execution())

    with pytest.raises(ExecutionLineageConflictError):
        store.create_execution(conflict)

    assert store.load_execution("execution-1") == execution()


def test_expected_state_replacement_and_safe_current_state_replay(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    source = execution()
    destination = execution(ExecutionStatus.IN_PROGRESS)
    store.create_execution(source)

    assert store.replace_execution(destination, expected_execution=source) == destination
    assert store.replace_execution(destination, expected_execution=destination) == destination
    assert store.load_execution("execution-1") == destination

    with pytest.raises(ExecutionLineageConflictError):
        store.create_execution(destination)


def test_stale_expected_state_cannot_replace_newer_state(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    source = execution()
    winner = execution(ExecutionStatus.IN_PROGRESS)
    store.create_execution(source)
    store.replace_execution(winner, expected_execution=source)

    with pytest.raises(ExecutionLineageStaleStateError):
        store.replace_execution(
            execution(ExecutionStatus.UNCONFIRMED),
            expected_execution=source,
        )

    assert store.load_execution("execution-1") == winner


def test_two_competing_transitions_allow_exactly_one_mutation(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    source = execution()
    store.create_execution(source)
    barrier = Barrier(2)

    def replace(status):
        barrier.wait()
        try:
            store.replace_execution(execution(status), expected_execution=source)
            return "saved"
        except ExecutionLineageStaleStateError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(
            replace,
            (ExecutionStatus.IN_PROGRESS, ExecutionStatus.UNCONFIRMED),
        ))

    assert sorted(outcomes) == ["saved", "stale"]
    assert store.load_execution("execution-1").status in {
        ExecutionStatus.IN_PROGRESS,
        ExecutionStatus.UNCONFIRMED,
    }


def test_two_competing_terminal_transitions_allow_exactly_one_mutation(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    initial = execution()
    source = execution(ExecutionStatus.IN_PROGRESS)
    store.create_execution(initial)
    store.replace_execution(source, expected_execution=initial)
    barrier = Barrier(2)

    def replace(status):
        barrier.wait()
        try:
            store.replace_execution(execution(status), expected_execution=source)
            return "saved"
        except ExecutionLineageStaleStateError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(
            replace,
            (ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED),
        ))

    assert sorted(outcomes) == ["saved", "stale"]
    assert store.load_execution("execution-1").status in {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.INTERRUPTED,
    }


def test_evidence_append_reloads_after_reconstruction_and_replays(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    store.create_execution(execution())
    source = evidence()

    assert store.append_evidence(source) == source
    assert store.append_evidence(source) == source
    assert FileExecutionLineageStore(tmp_path).load_evidence("evidence-1") == source


def test_conflicting_or_cross_execution_evidence_fails(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    store.create_execution(execution())
    store.create_execution(execution(execution_id="execution-2", mission_id="mission-2"))
    store.append_evidence(evidence())

    with pytest.raises(ExecutionLineageConflictError):
        store.append_evidence(evidence(FieldOutcomeEvidence))
    with pytest.raises(ExecutionLineageConflictError):
        store.append_evidence(evidence(execution_id="execution-2"))


def test_concurrent_evidence_appends_preserve_both_records(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    store.create_execution(execution())
    barrier = Barrier(2)

    def append(evidence_id):
        barrier.wait()
        return store.append_evidence(evidence(evidence_id=evidence_id))

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(append, ("evidence-1", "evidence-2")))

    assert store.load_evidence("evidence-1").evidence_id == "evidence-1"
    assert store.load_evidence("evidence-2").evidence_id == "evidence-2"


def test_concurrent_transition_and_evidence_append_preserve_both(tmp_path):
    store = FileExecutionLineageStore(tmp_path)
    source = execution()
    store.create_execution(source)
    barrier = Barrier(2)

    def transition():
        barrier.wait()
        return store.replace_execution(
            execution(ExecutionStatus.IN_PROGRESS),
            expected_execution=source,
        )

    def append():
        barrier.wait()
        return store.append_evidence(evidence())

    with ThreadPoolExecutor(max_workers=2) as executor:
        transition_result = executor.submit(transition)
        evidence_result = executor.submit(append)
        transition_result.result()
        evidence_result.result()

    assert store.load_execution("execution-1").status is ExecutionStatus.IN_PROGRESS
    assert store.load_evidence("evidence-1") == evidence()


def test_unknown_execution_and_evidence_are_explicitly_not_found(tmp_path):
    store = FileExecutionLineageStore(tmp_path)

    with pytest.raises(ExecutionLineageNotFoundError, match="execution_not_found"):
        store.load_execution("execution-1")
    with pytest.raises(ExecutionLineageNotFoundError, match="evidence_not_found"):
        store.load_evidence("evidence-1")


@pytest.mark.parametrize("corruption", ("json", "schema", "non_integer_schema"))
def test_corrupt_or_unsupported_schema_fails_closed(tmp_path, corruption):
    store = FileExecutionLineageStore(tmp_path)
    store.create_execution(execution())
    path = tmp_path / "execution-1.json"
    if corruption == "json":
        path.write_text("{broken", encoding="utf-8")
    else:
        document = json.loads(path.read_text(encoding="utf-8"))
        document["schema_version"] = (
            2 if corruption == "schema" else 1.0
        )
        path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExecutionLineageCorruptionError):
        store.load_execution("execution-1")


def test_atomic_replace_failure_preserves_previous_aggregate(tmp_path, monkeypatch):
    store = FileExecutionLineageStore(tmp_path)
    source = execution()
    store.create_execution(source)
    path = tmp_path / "execution-1.json"
    before = path.read_bytes()
    monkeypatch.setattr(
        store_module.os,
        "replace",
        lambda *args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        store.replace_execution(
            execution(ExecutionStatus.IN_PROGRESS),
            expected_execution=source,
        )

    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".execution-1.*.tmp"))


def test_unique_temporary_files_are_cleaned(tmp_path, monkeypatch):
    store = FileExecutionLineageStore(tmp_path)
    replaced = []
    original_replace = store_module.os.replace

    def observe_replace(source, destination):
        replaced.append(source.name)
        return original_replace(source, destination)

    monkeypatch.setattr(store_module.os, "replace", observe_replace)
    store.create_execution(execution())
    store.create_execution(execution(execution_id="execution-2", mission_id="mission-2"))

    assert len(set(replaced)) == 2
    assert not list(tmp_path.glob(".*.tmp"))
