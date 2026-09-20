from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Protocol

from decision.mission.night_mission import NightMission
from decision.models.session_availability import SessionAvailability
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.services.user_selection_validator import (
    UserSelectionDecisionContext,
    validate_user_selection,
)
from decision.services.selected_imaging_field_resolution import (
    SelectedAcquisitionIntentResolutionError,
    SelectedImagingFieldResolutionError,
    acquisition_intent_provenance_expected,
    resolve_selected_acquisition_intent_id,
    resolve_selected_imaging_field_id,
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


@dataclass(frozen=True, slots=True)
class DecisionAcceptanceResult:
    selection: UserSelection
    mission: NightMission | None


class DecisionAcceptanceContextStore(Protocol):
    def save(self, context: DecisionAcceptanceContext) -> None: ...

    def load(self, *, decision_id: str) -> DecisionAcceptanceContext | None: ...

    def commit_selection_and_mission(
        self,
        selection: UserSelection,
        mission: NightMission | None,
        *,
        acceptance_request_id: str | None = None,
    ) -> tuple[UserSelection, NightMission | None]: ...

    def load_acceptance(
        self,
        acceptance_request_id: str,
    ) -> tuple[UserSelection, NightMission | None] | None: ...

    def load_selection(self, selection_id: str) -> UserSelection: ...

    def load_mission(self, mission_id: str) -> NightMission: ...


class InMemoryDecisionAcceptanceContextStore:
    """Keeps immutable decision snapshots for the lifetime of the application."""

    def __init__(self) -> None:
        self._contexts: dict[str, DecisionAcceptanceContext] = {}
        self._selections: dict[str, UserSelection] = {}
        self._missions: dict[str, NightMission] = {}
        self._acceptance_requests: dict[str, tuple[str, str | None]] = {}

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

    def commit_selection_and_mission(
        self,
        selection: UserSelection,
        mission: NightMission | None,
        *,
        acceptance_request_id: str | None = None,
    ) -> tuple[UserSelection, NightMission | None]:
        if acceptance_request_id is not None:
            existing = self.load_acceptance(acceptance_request_id)
            if existing is not None:
                existing_selection, existing_mission = existing
                if not _same_acceptance_payload(existing_selection, selection):
                    raise DecisionAcceptanceError(
                        "acceptance_request_conflict"
                    )
                return existing_selection, existing_mission
        existing_selection = self._selections.get(selection.selection_id)
        if existing_selection is not None:
            if existing_selection == selection and (
                mission is None
                or self._missions.get(mission.mission_id) == mission
            ):
                return existing_selection, mission
            raise DecisionAcceptanceError("selection_id_conflict")
        if mission is not None and mission.mission_id in self._missions:
            raise DecisionAcceptanceError("mission_id_conflict")
        if mission is not None and (
            mission.acquisition_intent_id
            != selection.selected_acquisition_intent_id
        ):
            raise DecisionAcceptanceError(
                "mission_acquisition_intent_mismatch"
            )
        self._selections[selection.selection_id] = deepcopy(selection)
        if mission is not None:
            self._missions[mission.mission_id] = mission
        if acceptance_request_id is not None:
            self._acceptance_requests[acceptance_request_id] = (
                selection.selection_id,
                None if mission is None else mission.mission_id,
            )
        return deepcopy(selection), mission

    def load_acceptance(
        self,
        acceptance_request_id: str,
    ) -> tuple[UserSelection, NightMission | None] | None:
        identities = self._acceptance_requests.get(acceptance_request_id)
        if identities is None:
            return None
        selection_id, mission_id = identities
        selection = self._selections[selection_id]
        mission = None if mission_id is None else self._missions[mission_id]
        return deepcopy(selection), mission

    def load_selection(self, selection_id: str) -> UserSelection:
        selection = self._selections.get(selection_id)
        if selection is None:
            raise DecisionAcceptanceError("selection_not_found")
        return deepcopy(selection)

    def load_mission(self, mission_id: str) -> NightMission:
        mission = self._missions.get(mission_id)
        if mission is None:
            raise DecisionAcceptanceError("mission_not_found")
        return mission


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_ACCEPTANCE_REQUEST_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
)


def _same_acceptance_payload(left: UserSelection, right: UserSelection) -> bool:
    return (
        left.decision_id,
        left.source,
        left.selected_catalog_key,
        left.selected_at,
        left.selected_acquisition_intent_id,
    ) == (
        right.decision_id,
        right.source,
        right.selected_catalog_key,
        right.selected_at,
        right.selected_acquisition_intent_id,
    )


def _same_acceptance_payload_without_intent(
    left: UserSelection,
    right: UserSelection,
) -> bool:
    return (
        left.decision_id,
        left.source,
        left.selected_catalog_key,
        left.selected_at,
    ) == (
        right.decision_id,
        right.source,
        right.selected_catalog_key,
        right.selected_at,
    )


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
        return self._accept_new(selection, acceptance_request_id=None).mission

    def accept_idempotently(
        self,
        selection: UserSelection,
        *,
        acceptance_request_id: str,
    ) -> DecisionAcceptanceResult:
        if not isinstance(selection, UserSelection):
            raise TypeError("Expected UserSelection")
        if (
            not isinstance(acceptance_request_id, str)
            or _ACCEPTANCE_REQUEST_ID_PATTERN.fullmatch(
                acceptance_request_id
            ) is None
        ):
            raise DecisionAcceptanceError("acceptance_request_id_required")
        try:
            committed = self.context_store.load_acceptance(
                acceptance_request_id
            )
        except OSError as exc:
            raise DecisionAcceptanceError(
                "decision_lineage_persistence_error"
            ) from exc
        except ValueError as exc:
            if isinstance(exc, DecisionAcceptanceError):
                raise
            raise DecisionAcceptanceError(str(exc)) from exc
        if committed is not None:
            canonical_selection, canonical_mission = committed
            if not _same_acceptance_payload_without_intent(
                canonical_selection,
                selection,
            ):
                raise DecisionAcceptanceError("acceptance_request_conflict")
            if (
                canonical_selection.selected_acquisition_intent_id is None
                and selection.selected_acquisition_intent_id is None
            ):
                return DecisionAcceptanceResult(
                    selection=canonical_selection,
                    mission=canonical_mission,
                )
            context = self.context_store.load(decision_id=selection.decision_id)
            if not isinstance(context, DecisionAcceptanceContext):
                raise DecisionAcceptanceError("decision_context_incomplete")
            try:
                proposed_selection = replace(
                    selection,
                    selected_acquisition_intent_id=(
                        resolve_selected_acquisition_intent_id(
                            context,
                            selection,
                        )
                    ),
                )
            except SelectedAcquisitionIntentResolutionError as exc:
                raise DecisionAcceptanceError(str(exc)) from exc
            if not _same_acceptance_payload(
                canonical_selection,
                proposed_selection,
            ):
                raise DecisionAcceptanceError("acceptance_request_conflict")
            return DecisionAcceptanceResult(
                selection=canonical_selection,
                mission=canonical_mission,
            )
        return self._accept_new(
            selection,
            acceptance_request_id=acceptance_request_id,
        )

    def _accept_new(
        self,
        selection: UserSelection,
        *,
        acceptance_request_id: str | None,
    ) -> DecisionAcceptanceResult:
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
        try:
            selection = replace(
                selection,
                selected_acquisition_intent_id=(
                    resolve_selected_acquisition_intent_id(
                        context,
                        selection,
                    )
                ),
                selected_imaging_field_id=resolve_selected_imaging_field_id(
                    context,
                    selection,
                ),
            )
        except (
            SelectedAcquisitionIntentResolutionError,
            SelectedImagingFieldResolutionError,
        ) as exc:
            raise DecisionAcceptanceError(str(exc)) from exc

        try:
            intent_provenance_expected = (
                acquisition_intent_provenance_expected(context, selection)
            )
        except SelectedAcquisitionIntentResolutionError as exc:
            raise DecisionAcceptanceError(str(exc)) from exc
        if (
            selection.selected_imaging_field_id is not None
            and selection.selected_acquisition_intent_id is None
            and intent_provenance_expected
        ):
            raise DecisionAcceptanceError(
                "acquisition_intent_required_for_mission"
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
            return self._commit_selection_and_mission(
                selection,
                None,
                acceptance_request_id=acceptance_request_id,
            )
        if not isinstance(mission, NightMission):
            raise DecisionAcceptanceError("mission_creation_failed")
        if (
            mission.mission_id != mission_id
            or mission.decision_id != selection.decision_id
            or mission.selection_id != selection.selection_id
        ):
            raise DecisionAcceptanceError("mission_provenance_mismatch")
        if mission.imaging_field_id != selection.selected_imaging_field_id:
            raise DecisionAcceptanceError("mission_imaging_field_mismatch")
        if (
            mission.acquisition_intent_id
            != selection.selected_acquisition_intent_id
        ):
            raise DecisionAcceptanceError(
                "mission_acquisition_intent_mismatch"
            )
        return self._commit_selection_and_mission(
            selection,
            mission,
            acceptance_request_id=acceptance_request_id,
        )

    def _commit_selection_and_mission(
        self,
        selection: UserSelection,
        mission: NightMission | None,
        *,
        acceptance_request_id: str | None,
    ) -> DecisionAcceptanceResult:
        try:
            if acceptance_request_id is None:
                self.context_store.commit_selection_and_mission(
                    selection,
                    mission,
                )
                canonical_selection, canonical_mission = selection, mission
            else:
                canonical_selection, canonical_mission = (
                    self.context_store.commit_selection_and_mission(
                        selection,
                        mission,
                        acceptance_request_id=acceptance_request_id,
                    )
                )
        except OSError as exc:
            raise DecisionAcceptanceError(
                "decision_lineage_persistence_error"
            ) from exc
        except ValueError as exc:
            if isinstance(exc, DecisionAcceptanceError):
                raise
            raise DecisionAcceptanceError(str(exc)) from exc
        return DecisionAcceptanceResult(
            selection=canonical_selection,
            mission=canonical_mission,
        )

    def load_selection(self, selection_id: str) -> UserSelection:
        try:
            return self.context_store.load_selection(selection_id)
        except ValueError as exc:
            if isinstance(exc, DecisionAcceptanceError):
                raise
            raise DecisionAcceptanceError(str(exc)) from exc

    def load_mission(self, mission_id: str) -> NightMission | None:
        try:
            return self.context_store.load_mission(mission_id)
        except ValueError as exc:
            if str(exc) == "mission_not_found":
                return None
            if isinstance(exc, DecisionAcceptanceError):
                raise
            raise DecisionAcceptanceError(str(exc)) from exc
