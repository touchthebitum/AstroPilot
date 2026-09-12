from __future__ import annotations

from collections.abc import Callable

from decision.execution_lineage_persistence import (
    ExecutionLineageConflictError,
    ExecutionLineageNotFoundError,
    ExecutionLineagePersistenceError,
    ExecutionLineageStaleStateError,
)
from decision.mission.night_mission import NightMission
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import OutcomeEvidence
from decision.services.execution_transition import validate_execution_transition


class ExecutionOutcomeApplicationError(ValueError):
    pass


class _InMemoryExecutionLineageStore:
    def __init__(self):
        self.executions: dict[str, Execution] = {}
        self.evidence: dict[str, OutcomeEvidence] = {}

    def create_execution(self, execution: Execution) -> Execution:
        current = self.executions.get(execution.execution_id)
        if current is not None:
            if current == execution:
                return current
            raise ExecutionLineageConflictError("execution_id_conflict")
        self.executions[execution.execution_id] = execution
        return execution

    def load_execution(self, execution_id: str) -> Execution:
        try:
            return self.executions[execution_id]
        except KeyError as error:
            raise ExecutionLineageNotFoundError("execution_not_found") from error

    def replace_execution(
        self,
        execution: Execution,
        *,
        expected_execution: Execution,
    ) -> Execution:
        current = self.load_execution(execution.execution_id)
        if current != expected_execution:
            raise ExecutionLineageStaleStateError("execution_stale_state")
        self.executions[execution.execution_id] = execution
        return execution

    def append_evidence(self, evidence: OutcomeEvidence) -> OutcomeEvidence:
        current = self.evidence.get(evidence.evidence_id)
        if current is not None:
            if current == evidence:
                return current
            raise ExecutionLineageConflictError("evidence_id_conflict")
        self.load_execution(evidence.execution_id)
        self.evidence[evidence.evidence_id] = evidence
        return evidence

    def load_evidence(self, evidence_id: str) -> OutcomeEvidence:
        try:
            return self.evidence[evidence_id]
        except KeyError as error:
            raise ExecutionLineageNotFoundError("evidence_not_found") from error


class ExecutionOutcomeApplicationService:
    """Explicit command boundary for mission execution and observed evidence."""

    def __init__(
        self,
        *,
        mission_loader: Callable[[str], NightMission | None],
        lineage_store=None,
    ):
        self.mission_loader = mission_loader
        self.lineage_store = (
            lineage_store
            if lineage_store is not None
            else _InMemoryExecutionLineageStore()
        )
        if isinstance(self.lineage_store, _InMemoryExecutionLineageStore):
            self._executions = self.lineage_store.executions
            self._evidence = self.lineage_store.evidence

    @staticmethod
    def _persistence_error(error: ExecutionLineagePersistenceError):
        raise ExecutionOutcomeApplicationError(str(error)) from error

    def create_execution(self, *, execution_id: str, mission_id: str) -> Execution:
        mission = self.mission_loader(mission_id)
        if mission is None:
            raise ExecutionOutcomeApplicationError("mission_not_found")
        if not isinstance(mission, NightMission) or mission.mission_id != mission_id:
            raise ExecutionOutcomeApplicationError("mission_identity_mismatch")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                mission.mission_id,
                mission.decision_id,
                mission.selection_id,
            )
        ):
            raise ExecutionOutcomeApplicationError("mission_provenance_required")
        created = Execution(
            execution_id=execution_id,
            mission_id=mission_id,
            status=ExecutionStatus.NOT_STARTED,
            actual_start=None,
            actual_end=None,
            actual_duration=None,
        )
        try:
            return self.lineage_store.create_execution(created)
        except ExecutionLineagePersistenceError as error:
            self._persistence_error(error)

    def load_execution(self, execution_id: str) -> Execution | None:
        try:
            return self.lineage_store.load_execution(execution_id)
        except ExecutionLineageNotFoundError:
            return None
        except ExecutionLineagePersistenceError as error:
            self._persistence_error(error)

    def load_outcome_evidence(self, evidence_id: str) -> OutcomeEvidence | None:
        try:
            return self.lineage_store.load_evidence(evidence_id)
        except ExecutionLineageNotFoundError:
            return None
        except ExecutionLineagePersistenceError as error:
            self._persistence_error(error)

    def transition_execution(self, destination: Execution) -> Execution:
        if not isinstance(destination, Execution):
            raise TypeError("Expected Execution")
        source = self.load_execution(destination.execution_id)
        if source is None:
            raise ExecutionOutcomeApplicationError("execution_not_found")
        validated = validate_execution_transition(source, destination)
        try:
            return self.lineage_store.replace_execution(
                validated,
                expected_execution=source,
            )
        except ExecutionLineagePersistenceError as error:
            self._persistence_error(error)

    def record_outcome_evidence(
        self,
        *,
        execution_id: str,
        evidence: OutcomeEvidence,
    ) -> OutcomeEvidence:
        execution = self.load_execution(execution_id)
        if execution is None:
            raise ExecutionOutcomeApplicationError("execution_not_found")
        if not isinstance(evidence, OutcomeEvidence):
            raise TypeError("Expected OutcomeEvidence")
        if evidence.execution_id != execution.execution_id:
            raise ExecutionOutcomeApplicationError("evidence_execution_mismatch")
        try:
            return self.lineage_store.append_evidence(evidence)
        except ExecutionLineagePersistenceError as error:
            self._persistence_error(error)
