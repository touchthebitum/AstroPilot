from datetime import datetime, timedelta, timezone

import pytest

from decision.execution_record import ExecutionRecord
from decision.execution_record_persistence import ExecutionRecordPersistenceError
from decision.field_observation import CloudCondition, FieldObservation
from decision.services.field_observation_recording_service import (
    FieldObservationRecordingError,
    FieldObservationRecordingService,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)


def observation(observation_id="observation-123", execution_id="execution-123"):
    return FieldObservation(
        observation_id=observation_id,
        execution_id=execution_id,
        observed_at_utc=OBSERVED_AT,
        cloud_condition=CloudCondition.CLEAR,
        transparency=None,
        seeing=None,
        dew_detected=None,
    )


def execution(execution_id="execution-123"):
    return ExecutionRecord(
        execution_id=execution_id,
        decision_id=None,
        started_at_utc=OBSERVED_AT - timedelta(hours=1),
        ended_at_utc=OBSERVED_AT + timedelta(hours=1),
        object="M31",
        hours=1.5,
    )


class ObservationStore:
    def __init__(self):
        self.saved = []

    def save(self, *, observation):
        self.saved.append(observation)

    def load(self, *, observation_id):
        raise AssertionError("service must not load observations")


class ExecutionStore:
    def __init__(self, record=None, error=None):
        self.record = execution() if record is None else record
        self.error = error
        self.loaded = []

    def load(self, *, execution_id):
        self.loaded.append(execution_id)
        if self.error is not None:
            raise self.error
        return self.record

    def save(self, *, execution):
        raise AssertionError("service must not create or save executions")


def service(execution_store=None):
    observation_store = ObservationStore()
    execution_store = execution_store or ExecutionStore()
    return (
        FieldObservationRecordingService(
            observation_store=observation_store,
            execution_store=execution_store,
        ),
        observation_store,
        execution_store,
    )


def test_existing_execution_allows_exact_observation_to_be_saved():
    recording, observation_store, execution_store = service()
    source = observation()

    recording.record_observation(source)

    assert execution_store.loaded == ["execution-123"]
    assert observation_store.saved == [source]


def test_missing_execution_fails_closed_before_observation_save():
    recording, observation_store, execution_store = service(
        ExecutionStore(record=None)
    )
    execution_store.record = None

    with pytest.raises(
        FieldObservationRecordingError,
        match="execution_record_missing",
    ):
        recording.record_observation(observation())

    assert execution_store.loaded == ["execution-123"]
    assert observation_store.saved == []


def test_corrupt_execution_fails_closed_before_observation_save():
    recording, observation_store, execution_store = service(
        ExecutionStore(
            error=ExecutionRecordPersistenceError("invalid_json_document")
        )
    )

    with pytest.raises(
        FieldObservationRecordingError,
        match="execution_record_invalid",
    ):
        recording.record_observation(observation())

    assert execution_store.loaded == ["execution-123"]
    assert observation_store.saved == []


def test_unexpected_execution_io_error_propagates_without_saving():
    error = OSError("execution filesystem unavailable")
    recording, observation_store, execution_store = service(
        ExecutionStore(error=error)
    )

    with pytest.raises(OSError) as raised:
        recording.record_observation(observation())

    assert raised.value is error
    assert execution_store.loaded == ["execution-123"]
    assert observation_store.saved == []


def test_multiple_observations_may_share_one_execution():
    recording, observation_store, execution_store = service()
    first = observation("observation-one")
    second = observation("observation-two")

    recording.record_observation(first)
    recording.record_observation(second)

    assert execution_store.loaded == ["execution-123", "execution-123"]
    assert observation_store.saved == [first, second]


def test_service_requires_preconstructed_field_observation():
    recording, observation_store, execution_store = service()

    with pytest.raises(
        FieldObservationRecordingError,
        match="invalid_field_observation",
    ):
        recording.record_observation(object())

    assert execution_store.loaded == []
    assert observation_store.saved == []


def test_service_has_no_decision_forecast_evidence_dependency():
    recording, observation_store, execution_store = service()

    assert vars(recording) == {
        "observation_store": observation_store,
        "execution_store": execution_store,
    }
