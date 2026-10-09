"""Opt-in explicit NightMerit execution caller; no background activity."""
from datetime import datetime
from threading import RLock

from decision.models.execution import ExecutionStatus
from decision.models.guardian import GuardianSessionState as State
from decision.models.guardian_live_session import GuardianLiveSessionEvidence


class GuardianSessionLifecycle:
    """One caller owns one authoritative store and one live execution.

    Timestamps are observations supplied by the caller, never execution-history
    timestamps chosen implicitly. Construction and reads cannot restore ownership.
    """

    def __init__(self, execution_service, store):
        self.execution_service = execution_service
        self.store = store
        self._owner = None
        self._lock = RLock()

    @staticmethod
    def _validate_time(observed_at):
        if not isinstance(observed_at, datetime) or observed_at.utcoffset() is None:
            raise ValueError("guardian_observation_timezone_required")

    def _write(self, state, session_id, observed_at):
        evidence = GuardianLiveSessionEvidence(
            state, observed_at, 'caller_session_heartbeat_v1',
            'CALLER_ASSERTED', session_id)
        try:
            self.store.write(evidence)
        except Exception:
            self._owner = None
            # Remove last-good evidence on failure. If removal also fails, its
            # error propagates with the original write error as context.
            self.store.path.unlink(missing_ok=True)
            raise
        return evidence

    def start(self, destination, *, observed_at):
        """Execute the user's start command, then attest its successful result."""
        self._validate_time(observed_at)
        with self._lock:
            if destination.status is not ExecutionStatus.IN_PROGRESS:
                raise ValueError('guardian_start_requires_in_progress')
            if self._owner is not None:
                raise ValueError('guardian_session_already_owned')
            result = self.execution_service.transition_execution(destination)
            evidence = self._write(State.ACTIVE, result.execution_id, observed_at)
            self._owner = result.execution_id
            return evidence

    def renew(self, execution_id, *, observed_at):
        """Explicit confirmation from this live owner, never a persisted-state poll."""
        self._validate_time(observed_at)
        with self._lock:
            if self._owner != execution_id:
                raise ValueError('guardian_session_not_owned')
            previous = self.store.read(observed_at)
            execution = self.execution_service.load_execution(execution_id)
            if (previous is None or previous.state is not State.ACTIVE
                    or previous.session_id != execution_id or execution is None
                    or execution.status is not ExecutionStatus.IN_PROGRESS):
                self._owner = None
                raise ValueError('guardian_session_attestation_lost')
            return self._write(State.ACTIVE, execution_id, observed_at)

    def stop(self, destination, *, observed_at):
        """Explicit completed/interrupted command; also usable after a restart."""
        self._validate_time(observed_at)
        with self._lock:
            if destination.status not in (ExecutionStatus.COMPLETED, ExecutionStatus.INTERRUPTED):
                raise ValueError('guardian_stop_requires_closed_execution')
            if self._owner not in (None, destination.execution_id):
                raise ValueError('guardian_session_not_owned')
            result = self.execution_service.transition_execution(destination)
            self._owner = None
            return self._write(State.INACTIVE, result.execution_id, observed_at)
