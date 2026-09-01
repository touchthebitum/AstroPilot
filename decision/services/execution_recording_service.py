from __future__ import annotations

from decision.execution_record import ExecutionRecord
from decision.execution_record_persistence import ExecutionRecordStore
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
    DecisionForecastEvidenceStore,
)


class ExecutionRecordingError(ValueError):
    pass


class ExecutionRecordingService:
    def __init__(
        self,
        *,
        execution_store: ExecutionRecordStore,
        evidence_store: DecisionForecastEvidenceStore,
    ) -> None:
        self.execution_store = execution_store
        self.evidence_store = evidence_store

    def record_execution(self, execution: ExecutionRecord) -> None:
        if not isinstance(execution, ExecutionRecord):
            raise ExecutionRecordingError("invalid_execution_record")

        if execution.decision_id is not None:
            try:
                evidence = self.evidence_store.load(
                    decision_id=execution.decision_id,
                )
            except DecisionForecastEvidencePersistenceError as error:
                raise ExecutionRecordingError(
                    "decision_evidence_invalid"
                ) from error
            if evidence is None:
                raise ExecutionRecordingError("decision_evidence_missing")

        self.execution_store.save(execution=execution)
