from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from decision.services.tonight_application_service import (
    TonightApplicationService,
    TonightResult,
)
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidenceStore,
)


def generate_decision_id() -> str:
    return str(uuid4())


class DurableTonightApplicationService:
    def __init__(
        self,
        *,
        application_service: TonightApplicationService,
        evidence_store: DecisionForecastEvidenceStore,
        decision_id_factory: Callable[[], str],
    ) -> None:
        self.application_service = application_service
        self.evidence_store = evidence_store
        self.decision_id_factory = decision_id_factory

    def evaluate(self, **kwargs) -> TonightResult:
        result = self.application_service.evaluate(**kwargs)
        if result.forecast_evidence is None:
            return result

        decision_id = self.decision_id_factory()
        self.evidence_store.save(
            decision_id=decision_id,
            evidence=result.forecast_evidence,
        )
        return replace(result, decision_id=decision_id)
