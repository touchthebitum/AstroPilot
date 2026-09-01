from datetime import datetime, timedelta, timezone

import pytest

from decision.execution_record import ExecutionRecord
from decision.services.execution_recording_service import (
    ExecutionRecordingError,
    ExecutionRecordingService,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)


START = datetime(2026, 9, 1, 20, tzinfo=timezone.utc)


def execution(execution_id="execution-123", decision_id=None):
    return ExecutionRecord(
        execution_id=execution_id,
        decision_id=decision_id,
        started_at_utc=START,
        ended_at_utc=START + timedelta(hours=2),
        object="M31",
        hours=1.5,
    )


class ExecutionStore:
    def __init__(self):
        self.saved = []

    def save(self, *, execution):
        self.saved.append(execution)

    def load(self, *, execution_id):
        raise AssertionError("service must not load execution records")


class EvidenceStore:
    def __init__(self, evidence=DecisionForecastEvidence(()), error=None):
        self.evidence = evidence
        self.error = error
        self.loaded = []

    def load(self, *, decision_id):
        self.loaded.append(decision_id)
        if self.error is not None:
            raise self.error
        return self.evidence

    def save(self, *, decision_id, evidence):
        raise AssertionError("service must not save decision evidence")


def service(evidence_store=None):
    execution_store = ExecutionStore()
    evidence_store = evidence_store or EvidenceStore()
    return (
        ExecutionRecordingService(
            execution_store=execution_store,
            evidence_store=evidence_store,
        ),
        execution_store,
        evidence_store,
    )


def test_manual_execution_is_saved_without_evidence_lookup():
    recording, execution_store, evidence_store = service()
    source = execution()

    recording.record_execution(source)

    assert execution_store.saved == [source]
    assert evidence_store.loaded == []


def test_execution_with_existing_decision_evidence_is_saved():
    recording, execution_store, evidence_store = service()
    source = execution(decision_id="decision-123")

    recording.record_execution(source)

    assert evidence_store.loaded == ["decision-123"]
    assert execution_store.saved == [source]


def test_missing_decision_evidence_fails_closed_without_saving():
    recording, execution_store, evidence_store = service(
        EvidenceStore(evidence=None)
    )

    with pytest.raises(
        ExecutionRecordingError,
        match="decision_evidence_missing",
    ):
        recording.record_execution(execution(decision_id="decision-123"))

    assert evidence_store.loaded == ["decision-123"]
    assert execution_store.saved == []


def test_corrupt_decision_evidence_fails_closed_without_saving():
    recording, execution_store, evidence_store = service(
        EvidenceStore(
            error=DecisionForecastEvidencePersistenceError(
                "invalid_json_document"
            )
        )
    )

    with pytest.raises(
        ExecutionRecordingError,
        match="decision_evidence_invalid",
    ):
        recording.record_execution(execution(decision_id="decision-123"))

    assert evidence_store.loaded == ["decision-123"]
    assert execution_store.saved == []


def test_unexpected_evidence_io_error_propagates_without_saving():
    error = OSError("evidence filesystem unavailable")
    recording, execution_store, evidence_store = service(
        EvidenceStore(error=error)
    )

    with pytest.raises(OSError) as raised:
        recording.record_execution(execution(decision_id="decision-123"))

    assert raised.value is error
    assert evidence_store.loaded == ["decision-123"]
    assert execution_store.saved == []


def test_multiple_executions_may_share_one_decision():
    recording, execution_store, evidence_store = service()
    first = execution("execution-one", "decision-123")
    second = execution("execution-two", "decision-123")

    recording.record_execution(first)
    recording.record_execution(second)

    assert evidence_store.loaded == ["decision-123", "decision-123"]
    assert execution_store.saved == [first, second]


def test_service_requires_an_execution_record():
    recording, execution_store, evidence_store = service()

    with pytest.raises(ExecutionRecordingError, match="invalid_execution_record"):
        recording.record_execution(object())

    assert evidence_store.loaded == []
    assert execution_store.saved == []
