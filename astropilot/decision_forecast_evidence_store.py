from __future__ import annotations

import os
import tempfile
from pathlib import Path

from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
    deserialize_decision_forecast_evidence,
    serialize_decision_forecast_evidence,
    validate_decision_id,
)


class FileDecisionForecastEvidenceStore:
    def __init__(self, directory: Path):
        self._directory = Path(directory)

    def _path(self, decision_id: str) -> Path:
        identity = validate_decision_id(decision_id)
        return self._directory / f"{identity}.json"

    def load(
        self,
        *,
        decision_id: str,
    ) -> DecisionForecastEvidence | None:
        path = self._path(decision_id)
        try:
            document = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except UnicodeError as error:
            raise DecisionForecastEvidencePersistenceError(
                "invalid_json_document"
            ) from error
        return deserialize_decision_forecast_evidence(
            document,
            decision_id=decision_id,
        )

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
        if path.exists():
            existing = self.load(decision_id=decision_id)
            if existing == evidence:
                return
            raise DecisionForecastEvidencePersistenceError(
                "decision_forecast_evidence_conflict"
            )

        self._directory.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
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
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
