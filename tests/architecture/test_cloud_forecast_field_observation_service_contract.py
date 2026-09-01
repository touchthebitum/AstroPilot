from datetime import datetime, timedelta, timezone

import pytest

from decision.execution_record import ExecutionRecord
from decision.execution_record_persistence import ExecutionRecordPersistenceError
from decision.field_observation import CloudCondition, FieldObservation
from decision.field_observation_persistence import (
    FieldObservationPersistenceError,
)
from decision.services.cloud_forecast_field_observation_service import (
    CloudForecastFieldObservationService,
    CloudForecastFieldObservationServiceError,
)
from decision.weather.cloud_forecast_evidence_comparison import (
    SelectedCloudForecastComparison,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import (
    DecisionForecastEvidencePersistenceError,
)
from decision.weather.forecast_temporal_selection import (
    ForecastTemporalSelectionError,
)
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)
LOCATION = WeatherLocation(46.7508, 6.5495)


def observation(*, cloud_condition=CloudCondition.FEW):
    return FieldObservation(
        observation_id="observation-123",
        execution_id="execution-456",
        observed_at_utc=OBSERVED_AT,
        cloud_condition=cloud_condition,
        transparency=None,
        seeing=None,
        dew_detected=(False if cloud_condition is None else None),
    )


def execution(*, decision_id="decision-789"):
    return ExecutionRecord(
        execution_id="execution-456",
        decision_id=decision_id,
        started_at_utc=OBSERVED_AT - timedelta(hours=1),
        ended_at_utc=OBSERVED_AT + timedelta(hours=1),
        object="M31",
        hours=1.5,
    )


def cloud_point(offset_minutes, cloud_cover_percent):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=OBSERVED_AT - timedelta(hours=2),
        forecast_for_utc=OBSERVED_AT + timedelta(minutes=offset_minutes),
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=(
            WeatherValue(
                variable=WeatherVariable.CLOUD_COVER_PERCENT,
                value=cloud_cover_percent,
                unit="%",
            ),
        ),
    )


class ObservationStore:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.loaded = []

    def load(self, *, observation_id):
        self.loaded.append(observation_id)
        if self.error is not None:
            raise self.error
        return self.value


class ExecutionStore:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.loaded = []

    def load(self, *, execution_id):
        self.loaded.append(execution_id)
        if self.error is not None:
            raise self.error
        return self.value


class EvidenceStore:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.loaded = []

    def load(self, *, decision_id):
        self.loaded.append(decision_id)
        if self.error is not None:
            raise self.error
        return self.value


def service(*, observation_store=None, execution_store=None, evidence_store=None):
    observation_store = observation_store or ObservationStore(observation())
    execution_store = execution_store or ExecutionStore(execution())
    evidence_store = evidence_store or EvidenceStore(
        DecisionForecastEvidence((cloud_point(0, 85.0),))
    )
    return (
        CloudForecastFieldObservationService(
            observation_store=observation_store,
            execution_store=execution_store,
            evidence_store=evidence_store,
        ),
        observation_store,
        execution_store,
        evidence_store,
    )


def compare(application, maximum_minutes=30):
    return application.compare(
        "observation-123",
        maximum_absolute_offset=timedelta(minutes=maximum_minutes),
    )


def test_missing_observation_is_an_application_error():
    application, observation_store, execution_store, evidence_store = service(
        observation_store=ObservationStore(None)
    )

    with pytest.raises(
        CloudForecastFieldObservationServiceError,
        match="^field_observation_missing$",
    ):
        compare(application)

    assert observation_store.loaded == ["observation-123"]
    assert execution_store.loaded == []
    assert evidence_store.loaded == []


def test_invalid_observation_store_data_is_translated_with_cause():
    cause = FieldObservationPersistenceError("invalid_json_document")
    application, _, execution_store, evidence_store = service(
        observation_store=ObservationStore(error=cause)
    )

    with pytest.raises(
        CloudForecastFieldObservationServiceError,
        match="^field_observation_invalid$",
    ) as raised:
        compare(application)

    assert raised.value.__cause__ is cause
    assert execution_store.loaded == []
    assert evidence_store.loaded == []


def test_missing_referenced_execution_is_an_application_error():
    application, _, execution_store, evidence_store = service(
        execution_store=ExecutionStore(None)
    )

    with pytest.raises(
        CloudForecastFieldObservationServiceError,
        match="^execution_record_missing$",
    ):
        compare(application)

    assert execution_store.loaded == ["execution-456"]
    assert evidence_store.loaded == []


def test_invalid_execution_store_data_is_translated_with_cause():
    cause = ExecutionRecordPersistenceError("invalid_json_document")
    application, _, _, evidence_store = service(
        execution_store=ExecutionStore(error=cause)
    )

    with pytest.raises(
        CloudForecastFieldObservationServiceError,
        match="^execution_record_invalid$",
    ) as raised:
        compare(application)

    assert raised.value.__cause__ is cause
    assert evidence_store.loaded == []


def test_manual_execution_returns_none_without_loading_evidence():
    application, _, _, evidence_store = service(
        execution_store=ExecutionStore(execution(decision_id=None))
    )

    assert compare(application) is None
    assert evidence_store.loaded == []


def test_missing_referenced_evidence_is_an_application_error():
    application, _, _, evidence_store = service(
        evidence_store=EvidenceStore(None)
    )

    with pytest.raises(
        CloudForecastFieldObservationServiceError,
        match="^decision_evidence_missing$",
    ):
        compare(application)

    assert evidence_store.loaded == ["decision-789"]


def test_invalid_evidence_store_data_is_translated_with_cause():
    cause = DecisionForecastEvidencePersistenceError("invalid_json_document")
    application, _, _, _ = service(
        evidence_store=EvidenceStore(error=cause)
    )

    with pytest.raises(
        CloudForecastFieldObservationServiceError,
        match="^decision_evidence_invalid$",
    ) as raised:
        compare(application)

    assert raised.value.__cause__ is cause


def test_happy_path_navigates_exact_ids_and_returns_cloud_comparison():
    source = observation(cloud_condition=CloudCondition.PARTLY_CLOUDY)
    point = cloud_point(-4, 85.0)
    application, observation_store, execution_store, evidence_store = service(
        observation_store=ObservationStore(source),
        execution_store=ExecutionStore(execution()),
        evidence_store=EvidenceStore(DecisionForecastEvidence((point,))),
    )

    result = compare(application)

    assert isinstance(result, SelectedCloudForecastComparison)
    assert result.forecast_point is point
    assert result.comparison.observed_condition is source.cloud_condition
    assert observation_store.loaded == ["observation-123"]
    assert execution_store.loaded == ["execution-456"]
    assert evidence_store.loaded == ["decision-789"]


def test_observation_without_cloud_returns_none_from_domain_pipeline():
    application, _, _, evidence_store = service(
        observation_store=ObservationStore(observation(cloud_condition=None))
    )

    assert compare(application) is None
    assert evidence_store.loaded == ["decision-789"]


def test_no_forecast_inside_forwarded_tolerance_returns_none():
    application, _, _, _ = service(
        evidence_store=EvidenceStore(
            DecisionForecastEvidence((cloud_point(10, 85.0),))
        )
    )

    assert compare(application, maximum_minutes=5) is None


def test_temporal_ambiguity_propagates_without_translation():
    application, _, _, _ = service(
        evidence_store=EvidenceStore(
            DecisionForecastEvidence(
                (cloud_point(-5, 5.0), cloud_point(5, 85.0))
            )
        )
    )

    with pytest.raises(
        ForecastTemporalSelectionError,
        match="^ambiguous_nearest_forecast$",
    ):
        compare(application)


def test_unexpected_store_io_error_propagates_unchanged():
    error = OSError("observation filesystem unavailable")
    application, _, _, _ = service(
        observation_store=ObservationStore(error=error)
    )

    with pytest.raises(OSError) as raised:
        compare(application)

    assert raised.value is error
