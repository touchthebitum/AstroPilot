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
from decision.services.execution_outcome_application import (
    ExecutionOutcomeApplicationService,
)
from decision.services.durable_portfolio_credit_application import (
    DurablePortfolioCreditApplicationService,
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
        clock: Callable | None = None,
        profile_loader: Callable | None = None,
        profile_saver: Callable | None = None,
    ) -> None:
        self.application_service = application_service
        self.evidence_store = evidence_store
        self.decision_id_factory = decision_id_factory
        self._acceptance_service = acceptance_service
        self.clock = clock
        self._execution_outcome_service = None
        self.profile_loader = profile_loader
        self.profile_saver = profile_saver
        self._portfolio_credit_service = None

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
                evidence_loader=self.evidence_store.load,
                clock=self.clock,
            )
        return self._acceptance_service

    def register_decision_context(self, **kwargs) -> None:
        self._decision_acceptance_service().register_decision(**kwargs)

    def accept(self, selection: UserSelection):
        return self._decision_acceptance_service().accept(selection)

    def _execution_outcome_application_service(
        self,
    ) -> ExecutionOutcomeApplicationService:
        if self._execution_outcome_service is None:
            self._execution_outcome_service = ExecutionOutcomeApplicationService(
                mission_loader=self._decision_acceptance_service().load_mission,
            )
        return self._execution_outcome_service

    def create_execution(self, *, execution_id: str, mission_id: str):
        return self._execution_outcome_application_service().create_execution(
            execution_id=execution_id,
            mission_id=mission_id,
        )

    def transition_execution(self, execution):
        return self._execution_outcome_application_service().transition_execution(
            execution
        )

    def record_outcome_evidence(self, *, execution_id: str, evidence):
        return self._execution_outcome_application_service().record_outcome_evidence(
            execution_id=execution_id,
            evidence=evidence,
        )

    def _durable_portfolio_credit_application_service(
        self,
    ) -> DurablePortfolioCreditApplicationService:
        if self.profile_loader is None or self.profile_saver is None:
            raise RuntimeError("portfolio_credit_persistence_unavailable")
        if self._portfolio_credit_service is None:
            execution_service = self._execution_outcome_application_service()
            self._portfolio_credit_service = DurablePortfolioCreditApplicationService(
                load_profile=self.profile_loader,
                save_profile=self.profile_saver,
                execution_loader=execution_service.load_execution,
                evidence_loader=execution_service.load_outcome_evidence,
            )
        return self._portfolio_credit_service

    def apply_portfolio_credit(self, application, credit):
        return self._durable_portfolio_credit_application_service().apply(
            application,
            credit,
        )
