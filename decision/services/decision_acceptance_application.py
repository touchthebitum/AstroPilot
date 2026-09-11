from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from decision.mission.night_mission import NightMission
from decision.models.session_availability import SessionAvailability
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
    validate_user_selection,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)
from decision.weather.weather_ingress import (
    WeatherIngressError,
    validate_weather_retrieval_freshness,
)


class DecisionAcceptanceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DecisionAcceptanceContext:
    decision_context: UserSelectionDecisionContext
    recommendation: object
    night: Mapping
    profile: Mapping
    availability: SessionAvailability | None


class DecisionAcceptanceContextStore(Protocol):
    def save(self, context: DecisionAcceptanceContext) -> None: ...

    def load(self, *, decision_id: str) -> DecisionAcceptanceContext | None: ...


class InMemoryDecisionAcceptanceContextStore:
    """Keeps immutable decision snapshots for the lifetime of the application."""

    def __init__(self) -> None:
        self._contexts: dict[str, DecisionAcceptanceContext] = {}

    def save(self, context: DecisionAcceptanceContext) -> None:
        if not isinstance(context, DecisionAcceptanceContext):
            raise TypeError("Expected DecisionAcceptanceContext")
        decision_id = context.decision_context.decision_id
        if decision_id in self._contexts:
            raise DecisionAcceptanceError("decision_context_conflict")
        self._contexts[decision_id] = deepcopy(context)

    def load(self, *, decision_id: str) -> DecisionAcceptanceContext | None:
        context = self._contexts.get(decision_id)
        return deepcopy(context) if context is not None else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionAcceptanceApplicationService:
    def __init__(
        self,
        *,
        selection_mission_service,
        context_store: DecisionAcceptanceContextStore,
        mission_id_factory: Callable[[], str],
        evidence_loader: Callable | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.selection_mission_service = selection_mission_service
        self.context_store = context_store
        self.mission_id_factory = mission_id_factory
        self.evidence_loader = evidence_loader
        self.clock = clock or _utc_now
        self._missions: dict[str, NightMission] = {}

    def _acceptance_time(self) -> datetime:
        value = self.clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise DecisionAcceptanceError("decision_context_stale")
        return value

    def _validate_forecast_freshness(
        self,
        *,
        decision_id: str,
        reference_time: datetime,
    ) -> None:
        if self.evidence_loader is None:
            raise DecisionAcceptanceError("decision_context_stale")
        try:
            evidence = self.evidence_loader(decision_id=decision_id)
        except (DecisionForecastEvidencePersistenceError, OSError) as exc:
            raise DecisionAcceptanceError("decision_context_stale") from exc
        if not isinstance(evidence, DecisionForecastEvidence):
            raise DecisionAcceptanceError("decision_context_stale")
        points = evidence.forecast_points
        if not points:
            raise DecisionAcceptanceError("decision_context_stale")
        retrieved_at = points[0].retrieved_at_utc
        if any(point.retrieved_at_utc != retrieved_at for point in points[1:]):
            raise DecisionAcceptanceError("decision_context_stale")
        try:
            validate_weather_retrieval_freshness(
                retrieved_at,
                reference_time_utc=reference_time,
            )
        except WeatherIngressError as exc:
            raise DecisionAcceptanceError("decision_context_stale") from exc

    def _validate_selected_window(
        self,
        *,
        context: DecisionAcceptanceContext,
        selection: UserSelection,
        reference_time: datetime,
    ) -> None:
        if selection.source is UserSelectionSource.DECLINED:
            return
        evaluations = context.night.get("object_evaluations")
        evaluation = (
            evaluations.get(selection.selected_catalog_key)
            if isinstance(evaluations, Mapping)
            else None
        )
        decision_context = (
            evaluation.get("decision_context")
            if isinstance(evaluation, Mapping)
            else None
        )
        session = getattr(decision_context, "session", None)
        window_end = getattr(session, "end_time", None)
        if (
            not isinstance(window_end, datetime)
            or window_end.tzinfo is None
            or window_end.utcoffset() is None
            or window_end.astimezone(timezone.utc)
            <= reference_time.astimezone(timezone.utc)
        ):
            raise DecisionAcceptanceError("decision_context_stale")

    def register_decision(
        self,
        *,
        decision_id: str,
        recommendation,
        night: Mapping,
        profile: Mapping,
        availability: SessionAvailability | None,
        primary_catalog_key: str | None,
        exposed_alternative_catalog_keys: tuple[str, ...],
        explicitly_evaluated_catalog_keys: tuple[str, ...],
    ) -> None:
        context = DecisionAcceptanceContext(
            decision_context=UserSelectionDecisionContext(
                decision_id=decision_id,
                primary_catalog_key=primary_catalog_key,
                exposed_alternative_catalog_keys=exposed_alternative_catalog_keys,
                explicitly_evaluated_catalog_keys=explicitly_evaluated_catalog_keys,
            ),
            recommendation=recommendation,
            night=night,
            profile=profile,
            availability=availability,
        )
        self.context_store.save(context)

    def accept(self, selection: UserSelection) -> NightMission | None:
        if not isinstance(selection, UserSelection):
            raise TypeError("Expected UserSelection")
        context = self.context_store.load(decision_id=selection.decision_id)
        if context is None:
            raise DecisionAcceptanceError("decision_context_not_found")
        decision_context = getattr(context, "decision_context", None)
        if not isinstance(decision_context, UserSelectionDecisionContext):
            raise DecisionAcceptanceError("decision_context_incomplete")
        if decision_context.decision_id != selection.decision_id:
            raise DecisionAcceptanceError("decision_context_mismatch")
        if not isinstance(context, DecisionAcceptanceContext):
            raise DecisionAcceptanceError("decision_context_incomplete")

        reference_time = self._acceptance_time()
        self._validate_forecast_freshness(
            decision_id=selection.decision_id,
            reference_time=reference_time,
        )
        validate_user_selection(selection, decision_context)
        self._validate_selected_window(
            context=context,
            selection=selection,
            reference_time=reference_time,
        )

        mission_id = self.mission_id_factory()
        if not isinstance(mission_id, str) or not mission_id.strip():
            raise DecisionAcceptanceError("mission_id_required")
        mission = self.selection_mission_service.create(
            mission_id=mission_id,
            selection=selection,
            decision_context=context.decision_context,
            recommendation=context.recommendation,
            night=context.night,
            profile=context.profile,
            availability=context.availability,
        )
        if selection.source is UserSelectionSource.DECLINED:
            if mission is not None:
                raise DecisionAcceptanceError("declined_selection_created_mission")
            return None
        if not isinstance(mission, NightMission):
            raise DecisionAcceptanceError("mission_creation_failed")
        if (
            mission.mission_id != mission_id
            or mission.decision_id != selection.decision_id
            or mission.selection_id != selection.selection_id
        ):
            raise DecisionAcceptanceError("mission_provenance_mismatch")
        if mission_id in self._missions:
            raise DecisionAcceptanceError("mission_id_conflict")
        self._missions[mission_id] = mission
        return mission

    def load_mission(self, mission_id: str) -> NightMission | None:
        return self._missions.get(mission_id)
