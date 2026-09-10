from decision.models.execution import Execution, ExecutionStatus


class ExecutionTransitionError(ValueError):
    pass


ALLOWED_EXECUTION_TRANSITIONS = frozenset(
    {
        (ExecutionStatus.NOT_STARTED, ExecutionStatus.IN_PROGRESS),
        (ExecutionStatus.NOT_STARTED, ExecutionStatus.UNCONFIRMED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.COMPLETED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.INTERRUPTED),
        (ExecutionStatus.IN_PROGRESS, ExecutionStatus.UNCONFIRMED),
    }
)


def validate_execution_transition(
    source: Execution,
    destination: Execution,
) -> Execution:
    if not isinstance(source, Execution) or not isinstance(destination, Execution):
        raise TypeError("Expected Execution source and destination")
    if (
        source.execution_id != destination.execution_id
        or source.mission_id != destination.mission_id
    ):
        raise ExecutionTransitionError("execution_transition_identity_mismatch")
    if (source.status, destination.status) not in ALLOWED_EXECUTION_TRANSITIONS:
        raise ExecutionTransitionError("execution_transition_not_allowed")
    return destination
