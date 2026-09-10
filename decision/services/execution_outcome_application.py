from __future__ import annotations

from collections.abc import Callable

from decision.mission.night_mission import NightMission
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import OutcomeEvidence
from decision.services.execution_transition import validate_execution_transition


class ExecutionOutcomeApplicationError(ValueError):
    pass


class ExecutionOutcomeApplicationService:
    """Explicit command boundary for mission execution and observed evidence."""

    def __init__(self, *, mission_loader: Callable[[str], NightMission | None]):
        self.mission_loader = mission_loader
        self._executions: dict[str, Execution] = {}
        self._evidence: dict[str, OutcomeEvidence] = {}

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
        if execution_id in self._executions:
            raise ExecutionOutcomeApplicationError("execution_id_conflict")

        created = Execution(
            execution_id=execution_id,
            mission_id=mission_id,
            status=ExecutionStatus.NOT_STARTED,
            actual_start=None,
            actual_end=None,
            actual_duration=None,
        )
        self._executions[execution_id] = created
        return created

    def load_execution(self, execution_id: str) -> Execution | None:
        return self._executions.get(execution_id)

    def transition_execution(self, destination: Execution) -> Execution:
        if not isinstance(destination, Execution):
            raise TypeError("Expected Execution")
        source = self._executions.get(destination.execution_id)
        if source is None:
            raise ExecutionOutcomeApplicationError("execution_not_found")
        validated = validate_execution_transition(source, destination)
        self._executions[destination.execution_id] = validated
        return validated

    def record_outcome_evidence(
        self,
        *,
        execution_id: str,
        evidence: OutcomeEvidence,
    ) -> OutcomeEvidence:
        execution = self._executions.get(execution_id)
        if execution is None:
            raise ExecutionOutcomeApplicationError("execution_not_found")
        if not isinstance(evidence, OutcomeEvidence):
            raise TypeError("Expected OutcomeEvidence")
        if evidence.execution_id != execution.execution_id:
            raise ExecutionOutcomeApplicationError("evidence_execution_mismatch")
        if evidence.evidence_id in self._evidence:
            raise ExecutionOutcomeApplicationError("evidence_id_conflict")
        self._evidence[evidence.evidence_id] = evidence
        return evidence
