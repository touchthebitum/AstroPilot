from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from astropilot.file_lock import exclusive_file_lock
from astropilot.user_profile import get_user_data_dir
from decision.field_observation import (
    FieldObservation,
    validate_observation_identity,
)
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
            identity = validate_observation_identity(
                observation_id,
                field="observation_id",
            )
        except ValueError as error:
            raise FieldObservationPersistenceError(
                "invalid_observation_id"
            ) from error
        return self._directory / f"{identity}.json"

    def _locked(self):
        return exclusive_file_lock(
            self._directory / ".field_observations.lock"
        )

    def _load_path(self, path: Path) -> FieldObservation:
        try:
            document = path.read_text(encoding="utf-8")
        except UnicodeError as error:
            raise FieldObservationPersistenceError(
                "invalid_json_document"
            ) from error
        return deserialize_field_observation(
            document,
            observation_id=path.stem,
        )

    def load(self, *, observation_id: str) -> FieldObservation | None:
        path = self._path(observation_id)
        with self._locked():
            if not path.exists():
                return None
            return self._load_path(path)

    def _load_all(self) -> list[FieldObservation]:
        if not self._directory.exists():
            return []
        return [
            self._load_path(path)
            for path in sorted(self._directory.glob("*.json"))
        ]

    @staticmethod
    def _sorted(
        observations: list[FieldObservation],
    ) -> list[FieldObservation]:
        return sorted(
            observations,
            key=lambda item: (item.observed_at_utc, item.observation_id),
        )

    def list_by_decision(self, *, decision_id: str) -> list[FieldObservation]:
        try:
            identity = validate_observation_identity(
                decision_id,
                field="decision_id",
            )
        except ValueError as error:
            raise FieldObservationPersistenceError(
                "invalid_decision_id"
            ) from error
        with self._locked():
            return self._sorted(
                [
                    observation
                    for observation in self._load_all()
                    if observation.decision_id == identity
                ]
            )

    def list_by_execution(self, *, execution_id: str) -> list[FieldObservation]:
        try:
            identity = validate_observation_identity(
                execution_id,
                field="execution_id",
            )
        except ValueError as error:
            raise FieldObservationPersistenceError(
                "invalid_execution_id"
            ) from error
        with self._locked():
            return self._sorted(
                [
                    observation
                    for observation in self._load_all()
                    if observation.execution_id == identity
                ]
            )

    def _validate_supersession(self, observation: FieldObservation) -> None:
        superseded_id = observation.supersedes_observation_id
        if superseded_id is None:
            return
        superseded_path = self._path(superseded_id)
        if not superseded_path.exists():
            raise FieldObservationPersistenceError(
                "superseded_observation_missing"
            )
        superseded = self._load_path(superseded_path)
        if superseded.decision_id != observation.decision_id:
            raise FieldObservationPersistenceError(
                "superseded_observation_decision_mismatch"
            )

        visited = {observation.observation_id}
        current = superseded
        while current.supersedes_observation_id is not None:
            if current.observation_id in visited:
                raise FieldObservationPersistenceError(
                    "observation_supersession_cycle"
                )
            visited.add(current.observation_id)
            ancestor_path = self._path(current.supersedes_observation_id)
            if not ancestor_path.exists():
                raise FieldObservationPersistenceError(
                    "superseded_observation_missing"
                )
            current = self._load_path(ancestor_path)

    def save(self, *, observation: FieldObservation) -> bool:
        if type(observation) is not FieldObservation:
            raise FieldObservationPersistenceError(
                "invalid_field_observation"
            )
        path = self._path(observation.observation_id)
        document = serialize_field_observation(observation)
        with self._locked():
            if path.exists():
                existing = self._load_path(path)
                if existing == observation:
                    return False
                raise FieldObservationPersistenceError(
                    "field_observation_conflict"
                )
            self._validate_supersession(observation)
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
                    existing = self._load_path(path)
                    if existing == observation:
                        return False
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
        return True
