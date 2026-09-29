from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

from astropilot.file_lock import exclusive_file_lock
from astropilot.user_profile import get_user_data_dir
from decision.models.outcome_evaluation import OutcomeEvaluation
from decision.outcome_evaluation_persistence import (
    OutcomeEvaluationPersistenceError,
    deserialize_outcome_evaluation,
    serialize_outcome_evaluation,
)


_DIGEST = re.compile(r"[0-9a-f]{64}")


class FileOutcomeEvaluationStore:
    def __init__(self, directory: Path | None = None):
        self._directory = (
            Path(directory)
            if directory is not None
            else get_user_data_dir() / "outcome_evaluations"
        )

    def _path(self, evaluation_id: str) -> Path:
        if not isinstance(evaluation_id, str) or _DIGEST.fullmatch(evaluation_id) is None:
            raise OutcomeEvaluationPersistenceError("invalid_evaluation_id")
        return self._directory / f"{evaluation_id}.json"

    def _locked(self):
        return exclusive_file_lock(self._directory / ".outcome_evaluations.lock")

    def _load_path(self, path: Path) -> OutcomeEvaluation:
        try:
            document = path.read_text(encoding="utf-8")
            return deserialize_outcome_evaluation(document, evaluation_id=path.stem)
        except (OSError, UnicodeError, OutcomeEvaluationPersistenceError) as error:
            raise OutcomeEvaluationPersistenceError("outcome_evaluation_corrupt") from error

    def load(self, *, evaluation_id: str) -> OutcomeEvaluation | None:
        path = self._path(evaluation_id)
        with self._locked():
            if not path.exists():
                return None
            return self._load_path(path)

    def save(self, *, evaluation: OutcomeEvaluation) -> bool:
        if type(evaluation) is not OutcomeEvaluation:
            raise OutcomeEvaluationPersistenceError("invalid_outcome_evaluation")
        if not evaluation.comparison.identity_persistable:
            raise OutcomeEvaluationPersistenceError("comparison_identity_not_persistable")
        path = self._path(evaluation.evaluation_id)
        document = serialize_outcome_evaluation(evaluation)
        with self._locked():
            if path.exists():
                if self._load_path(path) == evaluation:
                    return False
                raise OutcomeEvaluationPersistenceError("outcome_evaluation_conflict")
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._directory,
                    prefix=f".{evaluation.evaluation_id}.",
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
                    if self._load_path(path) == evaluation:
                        return False
                    raise OutcomeEvaluationPersistenceError("outcome_evaluation_conflict")
            finally:
                if temporary_path is not None:
                    primary_error = sys.exception()
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        if primary_error is None:
                            raise
        return True

    def _load_all(self) -> list[OutcomeEvaluation]:
        if not self._directory.exists():
            return []
        return [self._load_path(path) for path in sorted(self._directory.glob("*.json"))]

    @staticmethod
    def _sorted(values: list[OutcomeEvaluation]) -> list[OutcomeEvaluation]:
        return sorted(values, key=lambda item: item.evaluation_id)

    def _list(self, predicate) -> list[OutcomeEvaluation]:
        with self._locked():
            return self._sorted([item for item in self._load_all() if predicate(item)])

    def list_by_observation(self, *, observation_id: str) -> list[OutcomeEvaluation]:
        if not isinstance(observation_id, str) or not observation_id.strip():
            raise OutcomeEvaluationPersistenceError("invalid_observation_id")
        return self._list(lambda item: item.comparison.observation_id == observation_id)

    def list_by_execution(self, *, execution_id: str) -> list[OutcomeEvaluation]:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise OutcomeEvaluationPersistenceError("invalid_execution_id")
        return self._list(lambda item: item.comparison.execution_id == execution_id)

    def list_by_comparison(self, *, comparison_id: str) -> list[OutcomeEvaluation]:
        if not isinstance(comparison_id, str) or _DIGEST.fullmatch(comparison_id) is None:
            raise OutcomeEvaluationPersistenceError("invalid_comparison_id")
        return self._list(lambda item: item.comparison.comparison_id == comparison_id)
