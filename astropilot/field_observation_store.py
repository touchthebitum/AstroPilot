from __future__ import annotations

from astropilot.field_lab_paths import require_user_directory
from astropilot.durable_read import json_document_paths

import os
import sys
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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
        require_user_directory(self._directory)
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
        require_user_directory(self._directory)
        return exclusive_file_lock(
            self._directory / ".field_observations.lock"
        )

    def _load_path(self, path: Path) -> FieldObservation:
        require_user_directory(self._directory)
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
        require_user_directory(self._directory)
        if not self._directory.exists():
            return []
        return [
            self._load_path(path)
            for path in json_document_paths(self._directory)
        ]

    @staticmethod
    def _lineage_by_id(
        observations: list[FieldObservation],
    ) -> dict[str, FieldObservation]:
        return {
            observation.observation_id: observation
            for observation in observations
        }

    @staticmethod
    def _children_by_parent(
        observations: list[FieldObservation],
    ) -> dict[str, list[FieldObservation]]:
        children: dict[str, list[FieldObservation]] = {}
        for observation in observations:
            parent_id = observation.supersedes_observation_id
            if parent_id is not None:
                children.setdefault(parent_id, []).append(observation)
        return children

    def _validate_active_lineage(
        self,
        *,
        observation: FieldObservation,
        observations: list[FieldObservation],
    ) -> None:
        by_id = self._lineage_by_id(observations)
        children = self._children_by_parent(observations)

        visited: set[str] = set()
        current = observation
        while True:
            if current.observation_id in visited:
                raise FieldObservationPersistenceError(
                    "field_observation_supersession_corrupt"
                )
            visited.add(current.observation_id)
            direct_children = children.get(current.observation_id, [])
            if len(direct_children) > 1:
                raise FieldObservationPersistenceError(
                    "field_observation_supersession_ambiguous"
                )
            if direct_children:
                child = direct_children[0]
                if child.decision_id != current.decision_id:
                    raise FieldObservationPersistenceError(
                        "field_observation_supersession_corrupt"
                    )
                current = child
                continue
            break

        current = observation
        while current.supersedes_observation_id is not None:
            parent = by_id.get(current.supersedes_observation_id)
            if parent is None or parent.decision_id != current.decision_id:
                raise FieldObservationPersistenceError(
                    "field_observation_supersession_corrupt"
                )
            if parent.observation_id in visited:
                raise FieldObservationPersistenceError(
                    "field_observation_supersession_corrupt"
                )
            visited.add(parent.observation_id)
            if len(children.get(parent.observation_id, [])) > 1:
                raise FieldObservationPersistenceError(
                    "field_observation_supersession_ambiguous"
                )
            current = parent

        if children.get(observation.observation_id):
            raise FieldObservationPersistenceError(
                "field_observation_superseded"
            )

    @contextmanager
    def active_observation_lease(
        self,
        *,
        observation_id: str,
    ) -> Iterator[FieldObservation]:
        path = self._path(observation_id)
        with self._locked():
            if not path.exists():
                raise FieldObservationPersistenceError(
                    "field_observation_missing"
                )
            observation = self._load_path(path)
            observations = self._load_all()
            self._validate_active_lineage(
                observation=observation,
                observations=observations,
            )
            yield observation

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

    def _load_catalogue_path(self, path: Path, before) -> FieldObservation:
        # Validate the opened file itself before reading: also protects platforms
        # without O_NOFOLLOW and refuses a file replaced during enumeration.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400
                    or not stat.S_ISREG(before.st_mode)
                    or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
                raise FieldObservationPersistenceError("observation_catalogue_unsafe_file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(1024 * 1024 + 1)
            after = path.lstat()
            if len(raw) > 1024 * 1024 or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise FieldObservationPersistenceError("observation_catalogue_changed")
            return deserialize_field_observation(raw.decode("utf-8"), observation_id=path.stem)
        finally:
            os.close(fd)

    def list_page(self, *, limit: int = 50, before: str | None = None):
        """Read this profile's saved reports, newest first; never omit corrupt data."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("invalid_observation_page")
        if before is not None:
            validate_observation_identity(before, field="observation_id")
        with self._locked():
            paths = json_document_paths(self._directory) if self._directory.exists() else []
            if len(paths) > 10000:
                raise FieldObservationPersistenceError("observation_catalogue_scan_limit")
            total = 0
            checked = []
            for path in paths:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise FieldObservationPersistenceError("observation_catalogue_unsafe_file")
                checked.append((path, info))
                total += info.st_size
                if info.st_size > 1024 * 1024 or total > 32 * 1024 * 1024:
                    raise FieldObservationPersistenceError("observation_catalogue_scan_limit")
            observations = sorted((self._load_catalogue_path(path, info) for path, info in checked),
                key=lambda item: (item.observed_at_utc, item.observation_id), reverse=True)
            if before is not None:
                anchor = next((o for o in observations if o.observation_id == before), None)
                if anchor is None:
                    raise ValueError("invalid_observation_page")
                observations = [o for o in observations if
                    (o.observed_at_utc, o.observation_id) < (anchor.observed_at_utc, anchor.observation_id)]
            items = observations[:limit]
            return {"items": items, "next_before": items[-1].observation_id if len(observations) > limit else None}

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
        if any(
            existing.supersedes_observation_id == superseded_id
            for existing in self._load_all()
        ):
            raise FieldObservationPersistenceError(
                "observation_already_superseded"
            )

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
