from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from astropilot.user_profile import get_user_data_dir
from decision.execution_record import validate_execution_identity
from decision.field_observation import FieldObservation
from decision.field_observation_persistence import (
    FieldObservationPersistenceError,
    deserialize_field_observation,
    serialize_field_observation,
)


class FileFieldObservationStore:
    def __init__(self, directory: Path | None = None):
        self._directory = (
            Path(directory)
            if directory is not None
            else get_user_data_dir() / "field_observations"
        )

    def _path(self, observation_id: str) -> Path:
        try:
            identity = validate_execution_identity(
                observation_id,
                field="observation_id",
            )
        except ValueError as error:
            raise FieldObservationPersistenceError(
                "invalid_observation_id"
            ) from error
        return self._directory / f"{identity}.json"

    def load(self, *, observation_id: str) -> FieldObservation | None:
        path = self._path(observation_id)
        try:
            document = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except UnicodeError as error:
            raise FieldObservationPersistenceError(
                "invalid_json_document"
            ) from error
        return deserialize_field_observation(
            document,
            observation_id=observation_id,
        )

    def save(self, *, observation: FieldObservation) -> None:
        if not isinstance(observation, FieldObservation):
            raise FieldObservationPersistenceError(
                "invalid_field_observation"
            )
        path = self._path(observation.observation_id)
        document = serialize_field_observation(observation)
        if path.exists():
            existing = self.load(observation_id=observation.observation_id)
            if existing == observation:
                return
            raise FieldObservationPersistenceError(
                "field_observation_conflict"
            )

        self._directory.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=f".{observation.observation_id}.",
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
                existing = self.load(
                    observation_id=observation.observation_id,
                )
                if existing != observation:
                    raise FieldObservationPersistenceError(
                        "field_observation_conflict"
                    )
        finally:
            if temporary_path is not None:
                primary_error = sys.exception()
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    if primary_error is None:
                        raise
