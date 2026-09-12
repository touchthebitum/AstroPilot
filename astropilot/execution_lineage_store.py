from __future__ import annotations

import fcntl
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from decision.execution_lineage_persistence import (
    ExecutionLineageAggregate,
    ExecutionLineageConflictError,
    ExecutionLineageCorruptionError,
    ExecutionLineageNotFoundError,
    ExecutionLineageStaleStateError,
    deserialize_execution_lineage_aggregate,
    serialize_execution_lineage_aggregate,
    validate_lineage_identity,
)
from decision.models.execution import Execution, ExecutionStatus
from decision.models.outcome_evidence import (
    AcquisitionOutcomeEvidence,
    FieldOutcomeEvidence,
    ImageOutcomeEvidence,
    OutcomeEvidence,
    TechnicalOutcomeEvidence,
)


_EVIDENCE_TYPES = (
    FieldOutcomeEvidence,
    TechnicalOutcomeEvidence,
    AcquisitionOutcomeEvidence,
    ImageOutcomeEvidence,
)


class FileExecutionLineageStore:
    def __init__(self, directory: Path):
        self._directory = Path(directory)

    def _path(self, execution_id: str) -> Path:
        identity = validate_lineage_identity(execution_id, field="execution_id")
        return self._directory / f"{identity}.json"

    @contextmanager
    def _locked(self):
        self._directory.mkdir(parents=True, exist_ok=True)
        lock_path = self._directory / ".execution_lineage.lock"
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _load_path(self, path: Path) -> ExecutionLineageAggregate:
        try:
            document = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise ExecutionLineageNotFoundError("execution_not_found") from error
        except UnicodeError as error:
            raise ExecutionLineageCorruptionError("invalid_json_document") from error
        return deserialize_execution_lineage_aggregate(
            document,
            execution_id=path.stem,
        )

    def _load_all(self) -> list[ExecutionLineageAggregate]:
        return [
            self._load_path(path)
            for path in sorted(self._directory.glob("*.json"))
        ]

    def _write(self, aggregate: ExecutionLineageAggregate) -> None:
        path = self._path(aggregate.execution_id)
        document = serialize_execution_lineage_aggregate(aggregate)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{aggregate.execution_id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(document)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                primary_error = sys.exception()
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    if primary_error is None:
                        raise

    def create_execution(self, execution: Execution) -> Execution:
        if type(execution) is not Execution:
            raise ExecutionLineageCorruptionError("invalid_execution")
        path = self._path(execution.execution_id)
        with self._locked():
            if path.exists():
                current = self._load_path(path).execution
                if (
                    current.status is ExecutionStatus.NOT_STARTED
                    and current == execution
                ):
                    return current
                raise ExecutionLineageConflictError("execution_id_conflict")
            if execution.status is not ExecutionStatus.NOT_STARTED:
                raise ExecutionLineageCorruptionError(
                    "execution_initial_state_invalid"
                )
            self._write(ExecutionLineageAggregate(execution))
        return execution

    def load_execution(self, execution_id: str) -> Execution:
        path = self._path(execution_id)
        with self._locked():
            if not path.exists():
                raise ExecutionLineageNotFoundError("execution_not_found")
            return self._load_path(path).execution

    def replace_execution(
        self,
        execution: Execution,
        *,
        expected_execution: Execution,
    ) -> Execution:
        if type(execution) is not Execution or type(expected_execution) is not Execution:
            raise ExecutionLineageCorruptionError("invalid_execution")
        if (
            execution.execution_id != expected_execution.execution_id
            or execution.mission_id != expected_execution.mission_id
        ):
            raise ExecutionLineageConflictError("execution_identity_mismatch")
        path = self._path(execution.execution_id)
        with self._locked():
            if not path.exists():
                raise ExecutionLineageNotFoundError("execution_not_found")
            aggregate = self._load_path(path)
            if aggregate.execution != expected_execution:
                raise ExecutionLineageStaleStateError("execution_stale_state")
            if aggregate.execution == execution:
                return aggregate.execution
            self._write(
                ExecutionLineageAggregate(
                    execution=execution,
                    evidence=aggregate.evidence,
                )
            )
        return execution

    def append_evidence(self, evidence: OutcomeEvidence) -> OutcomeEvidence:
        if type(evidence) not in _EVIDENCE_TYPES:
            raise ExecutionLineageCorruptionError("unsupported_evidence_type")
        path = self._path(evidence.execution_id)
        with self._locked():
            if not path.exists():
                raise ExecutionLineageNotFoundError("execution_not_found")
            aggregates = self._load_all()
            target = next(
                (
                    aggregate
                    for aggregate in aggregates
                    if aggregate.execution_id == evidence.execution_id
                ),
                None,
            )
            if target is None:
                raise ExecutionLineageNotFoundError("execution_not_found")
            matches = [
                (aggregate, record)
                for aggregate in aggregates
                for record in aggregate.evidence
                if record.evidence_id == evidence.evidence_id
            ]
            if matches:
                aggregate, current = matches[0]
                if (
                    len(matches) == 1
                    and aggregate.execution_id == evidence.execution_id
                    and current == evidence
                ):
                    return current
                raise ExecutionLineageConflictError("evidence_id_conflict")
            self._write(
                ExecutionLineageAggregate(
                    execution=target.execution,
                    evidence=target.evidence + (evidence,),
                )
            )
        return evidence

    def load_evidence(self, evidence_id: str) -> OutcomeEvidence:
        identity = validate_lineage_identity(evidence_id, field="evidence_id")
        with self._locked():
            matches = [
                record
                for aggregate in self._load_all()
                for record in aggregate.evidence
                if record.evidence_id == identity
            ]
            if not matches:
                raise ExecutionLineageNotFoundError("evidence_not_found")
            if len(matches) != 1:
                raise ExecutionLineageConflictError("evidence_id_conflict")
            return matches[0]
