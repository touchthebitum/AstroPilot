from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from decision.mission.night_mission import NightMission
from decision.models.session_availability import SessionAvailability
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.services.user_selection_validator import UserSelectionDecisionContext


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


class DecisionAcceptanceApplicationService:
    def __init__(
        self,
        *,
        selection_mission_service,
        context_store: DecisionAcceptanceContextStore,
        mission_id_factory: Callable[[], str],
    ) -> None:
        self.selection_mission_service = selection_mission_service
        self.context_store = context_store
        self.mission_id_factory = mission_id_factory
        self._missions: dict[str, NightMission] = {}

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
