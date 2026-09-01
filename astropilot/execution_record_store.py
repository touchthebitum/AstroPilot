from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from decision.execution_record import (
    ExecutionRecord,
    validate_execution_identity,
)
from decision.execution_record_persistence import (
    ExecutionRecordPersistenceError,
    deserialize_execution_record,
    serialize_execution_record,
)


class FileExecutionRecordStore:
    def __init__(self, directory: Path):
        self._directory = Path(directory)

    def _path(self, execution_id: str) -> Path:
        try:
            identity = validate_execution_identity(
                execution_id,
                field="execution_id",
            )
        except ValueError as error:
            raise ExecutionRecordPersistenceError(
                "invalid_execution_id"
            ) from error
        return self._directory / f"{identity}.json"

    def load(self, *, execution_id: str) -> ExecutionRecord | None:
        path = self._path(execution_id)
        try:
            document = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except UnicodeError as error:
            raise ExecutionRecordPersistenceError(
                "invalid_json_document"
            ) from error
        return deserialize_execution_record(
            document,
            execution_id=execution_id,
        )

    def save(self, *, execution: ExecutionRecord) -> None:
        if not isinstance(execution, ExecutionRecord):
            raise ExecutionRecordPersistenceError("invalid_execution_record")
        path = self._path(execution.execution_id)
        document = serialize_execution_record(execution)
        if path.exists():
            existing = self.load(execution_id=execution.execution_id)
            if existing == execution:
                return
            raise ExecutionRecordPersistenceError("execution_record_conflict")

        self._directory.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{execution.execution_id}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(document)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                existing = self.load(execution_id=execution.execution_id)
                if existing != execution:
                    raise ExecutionRecordPersistenceError(
                        "execution_record_conflict"
                    )
        finally:
            if temporary_path is not None:
                primary_error = sys.exception()
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    if primary_error is None:
                        raise
