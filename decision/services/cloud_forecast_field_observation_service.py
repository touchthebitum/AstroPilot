from datetime import timedelta

from decision.execution_record_persistence import (
    ExecutionRecordPersistenceError,
    ExecutionRecordStore,
)
from decision.field_observation_persistence import (
    FieldObservationPersistenceError,
    FieldObservationStore,
)
from decision.weather.cloud_forecast_evidence_comparison import (
    SelectedCloudForecastComparison,
)
from decision.weather.cloud_forecast_field_observation import (
    compare_cloud_forecast_to_field_observation,
)
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
    DecisionForecastEvidenceStore,
)


class CloudForecastFieldObservationServiceError(ValueError):
    pass


class CloudForecastFieldObservationService:
    def __init__(
        self,
        *,
        observation_store: FieldObservationStore,
        execution_store: ExecutionRecordStore,
        evidence_store: DecisionForecastEvidenceStore,
    ) -> None:
        self.observation_store = observation_store
        self.execution_store = execution_store
        self.evidence_store = evidence_store

    def compare(
        self,
        observation_id: str,
        *,
        maximum_absolute_offset: timedelta,
    ) -> SelectedCloudForecastComparison | None:
        try:
            observation = self.observation_store.load(
                observation_id=observation_id,
            )
        except FieldObservationPersistenceError as error:
            raise CloudForecastFieldObservationServiceError(
                "field_observation_invalid"
            ) from error
        if observation is None:
            raise CloudForecastFieldObservationServiceError(
                "field_observation_missing"
            )

        try:
            execution = self.execution_store.load(
                execution_id=observation.execution_id,
            )
        except ExecutionRecordPersistenceError as error:
            raise CloudForecastFieldObservationServiceError(
                "execution_record_invalid"
            ) from error
        if execution is None:
            raise CloudForecastFieldObservationServiceError(
                "execution_record_missing"
            )

        if execution.decision_id is None:
            return None

        try:
            evidence = self.evidence_store.load(
                decision_id=execution.decision_id,
            )
        except DecisionForecastEvidencePersistenceError as error:
            raise CloudForecastFieldObservationServiceError(
                "decision_evidence_invalid"
            ) from error
        if evidence is None:
            raise CloudForecastFieldObservationServiceError(
                "decision_evidence_missing"
            )

        return compare_cloud_forecast_to_field_observation(
            evidence,
            observation,
            maximum_absolute_offset=maximum_absolute_offset,
        )
