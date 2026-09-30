from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

from astropilot.durable_file_publication import (
    cleanup_temporary_files_durably,
    fsync_directory,
)
from astropilot.file_lock import exclusive_file_lock
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
    deserialize_decision_forecast_evidence,
    serialize_decision_forecast_evidence,
    validate_decision_id,
)


_TEMPORARY_NAME = re.compile(
    r"\.[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.[a-z0-9_]{8}\.tmp"
)


class FileDecisionForecastEvidenceStore:
    def __init__(self, directory: Path):
        self._directory = Path(directory)

    def _path(self, decision_id: str) -> Path:
        identity = validate_decision_id(decision_id)
        return self._directory / f"{identity}.json"

    def _locked(self):
        return exclusive_file_lock(
            self._directory / ".decision_forecast_evidence.lock"
        )

    def _load_path(
        self,
        path: Path,
        *,
        decision_id: str,
    ) -> DecisionForecastEvidence:
        try:
            document = path.read_text(encoding="utf-8")
        except UnicodeError as error:
            raise DecisionForecastEvidencePersistenceError(
                "invalid_json_document"
            ) from error
        return deserialize_decision_forecast_evidence(
            document,
            decision_id=decision_id,
        )

    def load(
        self,
        *,
        decision_id: str,
    ) -> DecisionForecastEvidence | None:
        path = self._path(decision_id)
        # Final documents are immutable and published by atomic hard-link, so a
        # read does not need to create or open the writer lock file.
        if not path.exists():
            return None
        return self._load_path(path, decision_id=decision_id)

    def save(
        self,
        *,
        decision_id: str,
        evidence: DecisionForecastEvidence,
    ) -> None:
        path = self._path(decision_id)
        document = serialize_decision_forecast_evidence(
            decision_id=decision_id,
            evidence=evidence,
        )
        with self._locked():
            temporary_path = None
            try:
                if path.exists():
                    existing = self._load_path(path, decision_id=decision_id)
                    if existing == evidence:
                        fsync_directory(self._directory)
                        return
                    raise DecisionForecastEvidencePersistenceError(
                        "decision_forecast_evidence_conflict"
                    )
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._directory,
                    prefix=f".{decision_id}.",
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
                    existing = self._load_path(path, decision_id=decision_id)
                    if existing != evidence:
                        raise DecisionForecastEvidencePersistenceError(
                            "decision_forecast_evidence_conflict"
                        )
                    fsync_directory(self._directory)
                else:
                    fsync_directory(self._directory)
            finally:
                cleanup_temporary_files_durably(
                    self._directory,
                    name_pattern=_TEMPORARY_NAME,
                    primary_error=sys.exception(),
                    synchronize_directory=fsync_directory,
                )
