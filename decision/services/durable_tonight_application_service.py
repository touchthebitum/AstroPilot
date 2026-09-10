from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from decision.models.user_selection import UserSelection
from decision.services.decision_acceptance_application import (
    DecisionAcceptanceApplicationService,
    InMemoryDecisionAcceptanceContextStore,
)
from decision.services.tonight_application_service import (
    TonightApplicationService,
    TonightResult,
)
from decision.services.user_selection_mission import UserSelectionMissionService
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidenceStore,
)


def generate_decision_id() -> str:
    return str(uuid4())


def generate_mission_id() -> str:
    return str(uuid4())


class DurableTonightApplicationService:
    def __init__(
        self,
        *,
        application_service: TonightApplicationService,
        evidence_store: DecisionForecastEvidenceStore,
        decision_id_factory: Callable[[], str],
        acceptance_service: DecisionAcceptanceApplicationService | None = None,
    ) -> None:
        self.application_service = application_service
        self.evidence_store = evidence_store
        self.decision_id_factory = decision_id_factory
        self._acceptance_service = acceptance_service

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

    def _decision_acceptance_service(self) -> DecisionAcceptanceApplicationService:
        if self._acceptance_service is None:
            self._acceptance_service = DecisionAcceptanceApplicationService(
                selection_mission_service=UserSelectionMissionService(
                    tonight_mission_service=(
                        self.application_service.tonight_mission_service
                    ),
                    build_mission_input=self.application_service.build_mission_input,
                ),
                context_store=InMemoryDecisionAcceptanceContextStore(),
                mission_id_factory=generate_mission_id,
            )
        return self._acceptance_service

    def register_decision_context(self, **kwargs) -> None:
        self._decision_acceptance_service().register_decision(**kwargs)

    def accept(self, selection: UserSelection):
        return self._decision_acceptance_service().accept(selection)
