from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from decision.models.user_selection import UserSelection
from decision.models.outcome_evaluation import (
    OUTCOME_EVALUATION_ALGORITHM_VERSION,
    OutcomeEvaluation,
)
from decision.services.decision_acceptance_application import (
    DecisionAcceptanceApplicationService,
    DecisionAcceptanceError,
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
from decision.services.intent_progress_credit import apply_execution_credit
from decision.services.user_selection_mission import UserSelectionMissionService
from decision.services.field_observation_context import (
    FieldObservationContextResolver,
)
from decision.services.field_observation_recording_service import (
    FieldObservationRecordingService,
)
from decision.services.outcome_evaluation_orchestration import (
    OutcomeEvaluationOrchestrationService,
    OutcomeEvaluationOrchestrationError,
)
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
        acceptance_lineage_store=None,
        execution_lineage_store=None,
        acceptance_service: DecisionAcceptanceApplicationService | None = None,
        clock: Callable | None = None,
        profile_loader: Callable | None = None,
        profile_saver: Callable | None = None,
        field_observation_store=None,
        outcome_evaluation_store=None,
        outcome_evaluation_clock: Callable | None = None,
        outcome_history_service=None,
        recent_decision_reader=None,
    ) -> None:
        self.application_service = application_service
        self.evidence_store = evidence_store
        self.decision_id_factory = decision_id_factory
        self.acceptance_lineage_store = acceptance_lineage_store
        self.execution_lineage_store = execution_lineage_store
        self._acceptance_service = acceptance_service
        self.clock = clock
        self._execution_outcome_service = None
        self.profile_loader = profile_loader
        self.profile_saver = profile_saver
        self._portfolio_credit_service = None
        self.field_observation_store = field_observation_store
        self._field_observation_service = None
        self.outcome_evaluation_store = outcome_evaluation_store
        self.outcome_evaluation_clock = outcome_evaluation_clock
        self._outcome_evaluation_service = None
        self.outcome_history_service = outcome_history_service
        self.recent_decision_reader = recent_decision_reader

    def read_recent_decisions(self, **filters):
        if self.recent_decision_reader is None:
            from astropilot.recent_decision_reader import RecentDecisionsUnavailable
            raise RecentDecisionsUnavailable("recent_decisions_unavailable")
        return self.recent_decision_reader.list_recent(**filters)

    def read_outcome_history(self, **filters):
        if self.outcome_history_service is None:
            from astropilot.outcome_history_reader import OutcomeHistoryUnavailable
            raise OutcomeHistoryUnavailable("outcome_history_unavailable")
        return self.outcome_history_service.history(**filters)

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
            context_store = self.acceptance_lineage_store
            if context_store is None:
                context_store = InMemoryDecisionAcceptanceContextStore()
            self._acceptance_service = DecisionAcceptanceApplicationService(
                selection_mission_service=UserSelectionMissionService(
                    tonight_mission_service=(
                        self.application_service.tonight_mission_service
                    ),
                    build_mission_input=self.application_service.build_mission_input,
                ),
                context_store=context_store,
                mission_id_factory=generate_mission_id,
                evidence_loader=self.evidence_store.load,
                clock=self.clock,
            )
        return self._acceptance_service

    def register_decision_context(self, **kwargs) -> None:
        self._decision_acceptance_service().register_decision(**kwargs)

    def accept(self, selection: UserSelection):
        return self._decision_acceptance_service().accept(selection)

    def accept_idempotently(
        self,
        selection: UserSelection,
        *,
        acceptance_request_id: str,
    ):
        return self._decision_acceptance_service().accept_idempotently(
            selection,
            acceptance_request_id=acceptance_request_id,
        )

    def load_selection(self, selection_id: str):
        return self._decision_acceptance_service().load_selection(selection_id)

    def load_mission(self, mission_id: str):
        return self._decision_acceptance_service().load_mission(mission_id)

    def session_read_snapshot(self):
        acceptance = self._decision_acceptance_service()
        factory = getattr(acceptance.context_store, "session_read_snapshot", None)
        if factory is None:
            return self
        try:
            snapshot = factory()
        except ValueError as exc:
            raise DecisionAcceptanceError(str(exc)) from exc
        scoped = copy.copy(self)
        scoped._acceptance_service = copy.copy(acceptance)
        scoped._acceptance_service.context_store = snapshot
        return scoped

    def latest_accepted_mission(self, *, profile, now):
        store = self._decision_acceptance_service().context_store
        if not hasattr(store, "latest_accepted_mission"):
            return None
        return store.latest_accepted_mission(profile=profile, now=now)

    def _execution_outcome_application_service(
        self,
    ) -> ExecutionOutcomeApplicationService:
        if self._execution_outcome_service is None:
            self._execution_outcome_service = ExecutionOutcomeApplicationService(
                mission_loader=self._decision_acceptance_service().load_mission,
                lineage_store=self.execution_lineage_store,
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

    def load_execution(self, execution_id: str):
        return self._execution_outcome_application_service().load_execution(
            execution_id
        )

    def load_session(self, execution_id: str):
        return self._execution_outcome_application_service().load_session(execution_id)

    def list_sessions(self, mission_id: str | None = None):
        return self._execution_outcome_application_service().list_sessions(mission_id)

    def load_outcome_evidence(self, evidence_id: str):
        return self._execution_outcome_application_service().load_outcome_evidence(
            evidence_id
        )

    @staticmethod
    def _optional_lineage_load(loader, identity):
        try:
            return loader(identity)
        except ValueError as error:
            if str(error).endswith("_not_found"):
                return None
            raise

    def _field_observation_recording_service(
        self,
    ) -> FieldObservationRecordingService:
        if self.field_observation_store is None:
            raise RuntimeError("field_observation_persistence_unavailable")
        if self._field_observation_service is None:
            acceptance = self._decision_acceptance_service()
            resolver = FieldObservationContextResolver(
                decision_evidence_loader=lambda decision_id: (
                    self.evidence_store.load(decision_id=decision_id)
                ),
                execution_loader=self.load_execution,
                mission_loader=lambda mission_id: self._optional_lineage_load(
                    acceptance.load_mission,
                    mission_id,
                ),
                selection_loader=lambda selection_id: self._optional_lineage_load(
                    acceptance.load_selection,
                    selection_id,
                ),
            )
            self._field_observation_service = FieldObservationRecordingService(
                observation_store=self.field_observation_store,
                context_resolver=resolver,
            )
        return self._field_observation_service

    def _outcome_evaluation_orchestration_service(
        self,
    ) -> OutcomeEvaluationOrchestrationService:
        if self.field_observation_store is None:
            raise RuntimeError("field_observation_persistence_unavailable")
        if self.outcome_evaluation_store is None:
            raise RuntimeError("outcome_evaluation_persistence_unavailable")
        if self.outcome_evaluation_clock is None:
            raise RuntimeError("outcome_evaluation_clock_unavailable")
        if self._outcome_evaluation_service is None:
            acceptance = self._decision_acceptance_service()
            resolver = FieldObservationContextResolver(
                decision_evidence_loader=lambda decision_id: (
                    self.evidence_store.load(decision_id=decision_id)
                ),
                execution_loader=self.load_execution,
                mission_loader=lambda mission_id: self._optional_lineage_load(
                    acceptance.load_mission,
                    mission_id,
                ),
                selection_loader=lambda selection_id: self._optional_lineage_load(
                    acceptance.load_selection,
                    selection_id,
                ),
            )
            self._outcome_evaluation_service = (
                OutcomeEvaluationOrchestrationService(
                    observation_store=self.field_observation_store,
                    forecast_evidence_store=self.evidence_store,
                    outcome_evaluation_store=self.outcome_evaluation_store,
                    context_resolver=resolver,
                    clock=self.outcome_evaluation_clock,
                )
            )
        return self._outcome_evaluation_service

    def record_field_observation(self, observation):
        return self._field_observation_recording_service().record_observation(
            observation
        )

    def evaluate_outcome_observation(self, observation_id: str):
        return self._outcome_evaluation_orchestration_service().evaluate(
            observation_id
        )

    def load_outcome_evaluation_by_observation(
        self, observation_id: str,
    ) -> OutcomeEvaluation | None:
        """Read the unique persisted v1 aggregate, including historical observations."""
        if self.outcome_evaluation_store is None:
            raise RuntimeError("outcome_evaluation_persistence_unavailable")
        candidates = tuple(
            item for item in self.outcome_evaluation_store.list_by_observation(
                observation_id=observation_id
            )
            if item.evaluation_algorithm_version == OUTCOME_EVALUATION_ALGORITHM_VERSION
        )
        if len(candidates) > 1:
            raise OutcomeEvaluationOrchestrationError("outcome_evaluation_conflict")
        return candidates[0] if candidates else None

    def load_field_observation(self, observation_id: str):
        if self.field_observation_store is None:
            raise RuntimeError("field_observation_persistence_unavailable")
        return self.field_observation_store.load(
            observation_id=observation_id
        )

    def list_field_observations_by_decision(self, decision_id: str):
        if self.field_observation_store is None:
            raise RuntimeError("field_observation_persistence_unavailable")
        return self.field_observation_store.list_by_decision(
            decision_id=decision_id
        )

    def list_field_observations_by_execution(self, execution_id: str):
        if self.field_observation_store is None:
            raise RuntimeError("field_observation_persistence_unavailable")
        return self.field_observation_store.list_by_execution(
            execution_id=execution_id
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

    def apply_intent_progress_credit(self, *, execution_id, evidence_ids,
                                     expected_revision, confirm_historical_baseline):
        if self.profile_loader is None or self.profile_saver is None:
            raise RuntimeError("intent_progress_persistence_unavailable")
        execution_service = self._execution_outcome_application_service()
        acceptance = self._decision_acceptance_service()
        return apply_execution_credit(
            profile=self.profile_loader(), execution_id=execution_id,
            evidence_ids=evidence_ids, expected_revision=expected_revision,
            confirm_historical_baseline=confirm_historical_baseline,
            load_execution=execution_service.load_execution,
            load_mission=acceptance.load_mission,
            load_selection=acceptance.load_selection,
            load_evidence=execution_service.load_outcome_evidence,
            save_profile=self.profile_saver,
        )
