"""Explicit process-owned commands. No background work or ownership recovery."""
from datetime import datetime, timedelta, timezone
import copy
import os
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import UUID, uuid4

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from astropilot.guardian_session_lifecycle import GuardianSessionLifecycle
from astropilot.guardian_session_store import GuardianSessionStore, PublicationValidationError
from decision.execution_lineage_persistence import (validate_lineage_identity,
    ExecutionLineageStaleStateError, ExecutionLineageConflictError)
from decision.models.execution import ExecutionStatus
from decision.models.guardian import GuardianSessionState
from decision.services.execution_transition import ExecutionTransitionError
from decision.services.execution_outcome_application import ExecutionOutcomeApplicationError

VERSION = 'guardian-explicit-renewal-v1'
TTL = timedelta(seconds=900)


class RenewalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal['guardian-explicit-renewal-v1']
    confirmation: Literal['USER_CONFIRMS_ACQUISITION_CONTINUES']
    owner_instance_id: str = Field(min_length=1)


class Rejection(PublicationValidationError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def stamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class WriterLock:
    """Persistent lock inode; never unlink it (including at shutdown)."""
    def __init__(self, path):
        self.path = path.with_name(path.name + '.writer.lock')
        self.handle = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0)
                self.handle.write(b'0')
                self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self.handle.close()
            self.handle = None
            raise RuntimeError('guardian_writer_exclusivity_unavailable') from None

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None


class GuardianRenewalAdapter:
    def __init__(self, service, path, clock, capacity=4096):
        path = Path(path)
        if not path.is_absolute() or capacity < 1:
            raise RuntimeError('guardian_configuration_invalid')
        path = path.resolve()
        self.clock = clock
        self.capacity = capacity
        self.command_lock = RLock()
        self.journal = {}
        self.owner_instance_id = str(uuid4())
        self.store = GuardianSessionStore(path, before_publish=self._before_publish)
        self.lifecycle = GuardianSessionLifecycle(service, self.store)
        self.writer_lock = WriterLock(path)
        self._publication_check = None
        self._last_clock = None
        self.writer_lock.acquire()

    def close(self):
        # In-flight commands finish before exclusivity is released.
        with self.command_lock:
            self.lifecycle.revoke()
            self.writer_lock.close()

    def now(self):
        try:
            value = self.clock()
            if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
                raise ValueError()
            return value
        except Exception:
            raise Rejection('guardian_clock_unavailable', 503) from None

    def _trusted_now(self, receipt):
        now = self.now()
        if now < receipt or (self._last_clock is not None and now < self._last_clock):
            raise Rejection('guardian_clock_unavailable', 503)
        self._last_clock = now
        if now - receipt > TTL:
            raise Rejection('guardian_confirmation_expired')
        return now

    def _before_publish(self):
        if self._publication_check is not None:
            self._publication_check()

    def error(self, code, execution_id, status=409, *, commit='not_attempted', publication='not_attempted', ownership=None):
        try:
            server_time = stamp(self.now())
        except Rejection:
            # Diagnostic wall time only; never used to authorize a command.
            server_time = stamp(datetime.now(timezone.utc))
        return status, dict(schema_version=VERSION, code=code, execution_id=execution_id,
            server_time=server_time, execution_commit=commit, guardian_publication=publication,
            ownership=ownership or ('retained' if self.lifecycle.owner_execution_id else 'lost'))

    def _execution(self, execution_id):
        try:
            result = self.lifecycle.execution_service.load_execution(execution_id)
        except Exception:
            raise Rejection('guardian_state_unavailable', 503) from None
        if result is None:
            raise Rejection('execution_not_found', 404)
        if result.execution_id != execution_id:
            raise Rejection('guardian_state_unavailable', 503)
        return result

    def _eligible(self, execution_id, now, *, revoke):
        execution = self._execution(execution_id)
        if self.lifecycle.owner_execution_id != execution_id:
            raise Rejection('guardian_session_not_owned')
        code = None
        if execution.status is not ExecutionStatus.IN_PROGRESS:
            code = 'guardian_execution_not_in_progress'
        try:
            evidence = self.store.read(now)
        except Exception:
            raise Rejection('guardian_state_unavailable', 503) from None
        if code is None and (evidence is None or evidence.state is not GuardianSessionState.ACTIVE or evidence.session_id != execution_id):
            code = 'guardian_session_attestation_lost'
        if code:
            if revoke:
                self.lifecycle.revoke()
            raise Rejection(code)
        return evidence

    def command(self, kind, execution_id, key, instance, semantic, receipt, destination=None):
        with self.command_lock:
            if instance != self.owner_instance_id:
                return self.error('guardian_owner_instance_mismatch', execution_id)
            fingerprint = (kind, execution_id, semantic)
            if key in self.journal:
                previous, result = self.journal[key]
                if previous != fingerprint:
                    return self.error('guardian_idempotency_conflict', execution_id)
                status, body = copy.deepcopy(result)
                if status == 200 and kind == 'renew':
                    try:
                        body.update(replayed=True, server_time=stamp(self.now()))
                    except Rejection as exc:
                        return self.error(exc.code, execution_id, exc.status)
                return status, body
            if len(self.journal) >= self.capacity:
                return self.error('guardian_command_capacity_exhausted', execution_id, 503)
            # Reserve before mutation. Even an unexpected terminal failure is retained.
            self.journal[key] = (fingerprint, self.error('guardian_command_failed', execution_id, 500, commit='unknown', publication='unknown', ownership='unknown'))
            commit = 'not_attempted'
            publication = 'not_attempted'
            try:
                now = self._trusted_now(receipt)
                self._execution(execution_id)
                if kind == 'transition':
                    if self.lifecycle.owner_execution_id is not None:
                        raise Rejection('guardian_session_not_owned')
                    commit = 'unknown'
                    result = 200, self.lifecycle.execution_service.transition_execution(destination)
                    self.journal[key] = fingerprint, result
                    return result
                if kind == 'renew':
                    evidence = self._eligible(execution_id, now, revoke=True)
                    if receipt < evidence.observed_at:
                        raise Rejection('guardian_confirmation_out_of_order')
                    self._eligible(execution_id, receipt, revoke=True)
                    def check():
                        self._eligible(execution_id, self._trusted_now(receipt), revoke=True)
                else:
                    previous = self.store.read(now)
                    if previous is not None and receipt < previous.observed_at:
                        raise Rejection('guardian_confirmation_out_of_order')
                    if self.lifecycle.owner_execution_id not in (None, execution_id):
                        raise Rejection('guardian_session_not_owned')
                    if kind == 'start' and self.lifecycle.owner_execution_id is not None:
                        raise Rejection('guardian_session_already_owned')
                    def check():
                        self._trusted_now(receipt)
                self._publication_check = check
                if kind == 'renew':
                    publication = 'unknown'
                    evidence = self.lifecycle.renew(execution_id, observed_at=receipt)
                    result = 200, dict(schema_version=VERSION, execution_id=execution_id,
                        owner_instance_id=self.owner_instance_id, confirmation_kind='USER_ASSERTION',
                        confirmed_at=stamp(evidence.observed_at), expires_at=stamp(evidence.observed_at + TTL),
                        server_time=stamp(self._last_clock), replayed=False)
                else:
                    # Observe service completion separately from publication.
                    commit = 'unknown'
                    original = self.lifecycle.execution_service
                    class TrackedService:
                        def transition_execution(self, value):
                            nonlocal commit, publication
                            result = original.transition_execution(value)
                            commit, publication = 'committed', 'unknown'
                            return result
                    self.lifecycle.execution_service = TrackedService()
                    try:
                        getattr(self.lifecycle, kind)(destination, observed_at=receipt)
                    finally:
                        self.lifecycle.execution_service = original
                    result = 200, destination
            except Rejection as exc:
                if exc.code in {'guardian_state_unavailable', 'guardian_clock_unavailable', 'execution_not_found'} and self.lifecycle.owner_execution_id == execution_id:
                    self.lifecycle.revoke()
                result = self.error(exc.code, execution_id, exc.status, commit=commit)
            except ExecutionTransitionError:
                result = self.error('guardian_execution_transition_rejected', execution_id, commit='not_committed')
            except ExecutionOutcomeApplicationError as exc:
                if isinstance(exc.__cause__, (ExecutionLineageStaleStateError, ExecutionLineageConflictError)):
                    commit = 'not_committed'
                elif commit == 'unknown' and self.lifecycle.owner_execution_id == execution_id:
                    self.lifecycle.revoke()
                code = 'execution_not_found' if str(exc) == 'execution_not_found' else 'guardian_execution_persistence_failed'
                result = self.error(code, execution_id, 404 if code == 'execution_not_found' else 503, commit=commit)
            except Exception:
                if publication == 'unknown':
                    result = self.error('guardian_attestation_publication_failed', execution_id, 503, commit=commit, publication='failed')
                elif commit == 'unknown':
                    if self.lifecycle.owner_execution_id == execution_id:
                        self.lifecycle.revoke()
                    result = self.error('guardian_execution_persistence_failed', execution_id, 503, commit='unknown')
                else:
                    result = self.error('guardian_command_failed', execution_id, 500, commit=commit, publication='unknown', ownership='unknown')
            finally:
                self._publication_check = None
            self.journal[key] = fingerprint, result
            return result

    def status(self, execution_id):
        with self.command_lock:
            try:
                now = self.now()
                if self._last_clock is not None and now < self._last_clock:
                    raise Rejection('guardian_clock_unavailable', 503)
                execution = self._execution(execution_id)
                try:
                    evidence = self._eligible(execution_id, now, revoke=False)
                    reason = None
                except Rejection as exc:
                    evidence, reason = None, exc.code
                return 200, dict(schema_version=VERSION, execution_id=execution_id,
                    execution_status=execution.status.value, guardian_mode_enabled=True,
                    owner_instance_id=self.owner_instance_id, owned_here=self.lifecycle.owner_execution_id == execution_id,
                    confirmation_kind='USER_ASSERTION' if evidence else None,
                    confirmed_at=stamp(evidence.observed_at) if evidence else None,
                    expires_at=stamp(evidence.observed_at + TTL) if evidence else None,
                    server_time=stamp(now), renewal_eligible=reason is None, ineligibility_reason=reason)
            except Rejection as exc:
                return self.error(exc.code, execution_id, exc.status)


def response(result):
    status, body = result
    return JSONResponse(status_code=status, content=body, headers={'Cache-Control': 'no-store'})


def valid_key(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise Rejection('invalid_guardian_renewal_request', 422) from None


def unavailable(code, execution_id, clock, status=409):
    try:
        now = clock()
        if now.utcoffset() != timedelta(0):
            raise ValueError()
    except Exception:
        now = datetime.now(timezone.utc)
    return response((status, dict(schema_version=VERSION, code=code,
        execution_id=execution_id, server_time=stamp(now), execution_commit='not_attempted',
        guardian_publication='not_attempted', ownership='unknown')))


def valid_execution_id(value):
    try:
        return validate_lineage_identity(value, field='execution_id')
    except ValueError:
        raise Rejection('invalid_guardian_renewal_request', 422) from None
