from __future__ import annotations

from dataclasses import dataclass

from decision.field_observation import FieldObservation
from decision.field_observation_persistence import FieldObservationStore
from decision.services.field_observation_context import (
    FieldObservationContextError,
    FieldObservationContextResolver,
    ResolvedFieldObservationContext,
)


class FieldObservationRecordingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FieldObservationRecordingResult:
    observation: FieldObservation
    resolved_context: ResolvedFieldObservationContext
    created: bool


class FieldObservationRecordingService:
    def __init__(
        self,
        *,
        observation_store: FieldObservationStore,
        context_resolver: FieldObservationContextResolver,
    ) -> None:
        self.observation_store = observation_store
        self.context_resolver = context_resolver

    def record_observation(
        self,
        observation: FieldObservation,
    ) -> FieldObservationRecordingResult:
        if type(observation) is not FieldObservation:
            raise FieldObservationRecordingError(
                "invalid_field_observation"
            )
        if observation.legacy_lineage_incomplete:
            raise FieldObservationRecordingError(
                "legacy_field_observation_read_only"
            )
        try:
            resolved_context = self.context_resolver.resolve(observation)
        except FieldObservationContextError as error:
            raise FieldObservationRecordingError(str(error)) from error
        created = self.observation_store.save(observation=observation)
        return FieldObservationRecordingResult(
            observation=observation,
            resolved_context=resolved_context,
            created=created,
        )
