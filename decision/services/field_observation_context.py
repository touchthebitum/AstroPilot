from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from decision.field_observation import FieldObservation
from decision.mission.night_mission import NightMission
from decision.models.execution import Execution, ExecutionStatus
from decision.models.user_selection import UserSelection
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence


class FieldObservationContextError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedFieldObservationContext:
    decision_id: str
    site_name: str | None
    latitude: float | None
    longitude: float | None
    target: str | None
    catalog_key: str | None
    imaging_field_id: str | None
    acquisition_intent_id: str | None
    mission_id: str | None
    execution_id: str | None
    execution_status: ExecutionStatus | None
    forecast_evidence_available: bool


class FieldObservationContextResolver:
    """Single read boundary for canonical decision/mission/execution lineage."""

    def __init__(
        self,
        *,
        decision_evidence_loader: Callable[[str], DecisionForecastEvidence | None],
        execution_loader: Callable[[str], Execution | None],
        mission_loader: Callable[[str], NightMission | None],
        selection_loader: Callable[[str], UserSelection | None],
    ) -> None:
        self.decision_evidence_loader = decision_evidence_loader
        self.execution_loader = execution_loader
        self.mission_loader = mission_loader
        self.selection_loader = selection_loader

    def resolve(
        self,
        observation: FieldObservation,
    ) -> ResolvedFieldObservationContext:
        if type(observation) is not FieldObservation:
            raise FieldObservationContextError("invalid_field_observation")
        if observation.decision_id is None:
            raise FieldObservationContextError("legacy_lineage_incomplete")

        evidence = self.decision_evidence_loader(observation.decision_id)
        if evidence is None:
            raise FieldObservationContextError("decision_not_found")
        if type(evidence) is not DecisionForecastEvidence:
            raise FieldObservationContextError("decision_evidence_invalid")

        location = (
            None
            if not evidence.forecast_points
            else evidence.forecast_points[0].requested_location
        )
        mission = None
        selection = None
        execution = None
        if observation.execution_id is not None:
            execution = self.execution_loader(observation.execution_id)
            if execution is None:
                raise FieldObservationContextError("execution_not_found")
            if type(execution) is not Execution:
                raise FieldObservationContextError("execution_invalid")
            if execution.execution_id != observation.execution_id:
                raise FieldObservationContextError("execution_identity_mismatch")
            mission = self.mission_loader(execution.mission_id)
            if mission is None:
                raise FieldObservationContextError("mission_not_found")
            if type(mission) is not NightMission:
                raise FieldObservationContextError("mission_invalid")
            if mission.mission_id != execution.mission_id:
                raise FieldObservationContextError("mission_identity_mismatch")
            if mission.decision_id != observation.decision_id:
                raise FieldObservationContextError(
                    "execution_decision_mismatch"
                )
            selection = self.selection_loader(mission.selection_id)
            if selection is None:
                raise FieldObservationContextError("selection_not_found")
            if type(selection) is not UserSelection:
                raise FieldObservationContextError("selection_invalid")
            if (
                selection.selection_id != mission.selection_id
                or selection.decision_id != observation.decision_id
            ):
                raise FieldObservationContextError(
                    "selection_decision_mismatch"
                )

        return ResolvedFieldObservationContext(
            decision_id=observation.decision_id,
            site_name=None if mission is None else mission.site_name,
            latitude=None if location is None else location.latitude,
            longitude=None if location is None else location.longitude,
            target=None if mission is None else mission.target,
            catalog_key=(
                None if selection is None else selection.selected_catalog_key
            ),
            imaging_field_id=(
                None if mission is None else mission.imaging_field_id
            ),
            acquisition_intent_id=(
                None if mission is None else mission.acquisition_intent_id
            ),
            mission_id=None if mission is None else mission.mission_id,
            execution_id=(
                None if execution is None else execution.execution_id
            ),
            execution_status=None if execution is None else execution.status,
            forecast_evidence_available=True,
        )
