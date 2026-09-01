from __future__ import annotations

from decision.execution_record_persistence import (
    ExecutionRecordPersistenceError,
    ExecutionRecordStore,
)
from decision.field_observation import FieldObservation
from decision.field_observation_persistence import FieldObservationStore


class FieldObservationRecordingError(ValueError):
    pass


class FieldObservationRecordingService:
    def __init__(
        self,
        *,
        observation_store: FieldObservationStore,
        execution_store: ExecutionRecordStore,
    ) -> None:
        self.observation_store = observation_store
        self.execution_store = execution_store

    def record_observation(self, observation: FieldObservation) -> None:
        if not isinstance(observation, FieldObservation):
            raise FieldObservationRecordingError(
                "invalid_field_observation"
            )

        try:
            execution = self.execution_store.load(
                execution_id=observation.execution_id,
            )
        except ExecutionRecordPersistenceError as error:
            raise FieldObservationRecordingError(
                "execution_record_invalid"
            ) from error
        if execution is None:
            raise FieldObservationRecordingError("execution_record_missing")

        self.observation_store.save(observation=observation)
