from datetime import datetime, timedelta, timezone

import pytest

from decision.field_observation import (
    CaptureMethod,
    CloudCondition,
    FieldObservation,
    ObservationProvenance,
    ObservationQuality,
    ObservationSourceType,
    ObservedAcquisition,
    ObservedConditions,
    ObservedTechnical,
)
from decision.field_observation_persistence import FieldObservationPersistenceError
from decision.services.cloud_forecast_field_observation_service import (
    CloudForecastFieldObservationService,
    CloudForecastFieldObservationServiceError,
)
from decision.weather.cloud_forecast_evidence_comparison import SelectedCloudForecastComparison
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import DecisionForecastEvidencePersistenceError
from decision.weather.forecast_temporal_selection import ForecastTemporalSelectionError
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


OBSERVED_AT = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)
LOCATION = WeatherLocation(46.7508, 6.5495)


def observation(*, cloud_condition=CloudCondition.FEW):
    conditions = ObservedConditions(cloud_state=cloud_condition)
    if cloud_condition is None:
        conditions = ObservedConditions(moon_halo=False)
    return FieldObservation(
        observation_id="observation-123",
        decision_id="decision-789",
        execution_id=None,
        observed_at_utc=OBSERVED_AT,
        recorded_at_utc=OBSERVED_AT,
        supersedes_observation_id=None,
        conditions=conditions,
        acquisition=ObservedAcquisition(),
        technical=ObservedTechnical(),
        provenance=ObservationProvenance(
            source_type=ObservationSourceType.USER,
            capture_method=CaptureMethod.MANUAL,
        ),
        quality=ObservationQuality(),
    )


def cloud_point(offset_minutes, cloud_cover_percent):
    return WeatherForecastPoint(
        provider_id="open_meteo",
        retrieved_at_utc=OBSERVED_AT - timedelta(hours=2),
        forecast_for_utc=OBSERVED_AT + timedelta(minutes=offset_minutes),
        requested_location=LOCATION,
        grid_location=LOCATION,
        values=(WeatherValue(
            variable=WeatherVariable.CLOUD_COVER_PERCENT,
            value=cloud_cover_percent,
            unit="%",
        ),),
    )


class Store:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.loaded = []

    def load(self, **identity):
        self.loaded.append(identity)
        if self.error is not None:
            raise self.error
        return self.value


def service(*, observation_store=None, evidence_store=None):
    observation_store = observation_store or Store(observation())
    evidence_store = evidence_store or Store(
        DecisionForecastEvidence((cloud_point(0, 85.0),))
    )
    return (
        CloudForecastFieldObservationService(
            observation_store=observation_store,
            evidence_store=evidence_store,
        ),
        observation_store,
        evidence_store,
    )


def compare(application, maximum_minutes=30):
    return application.compare(
        "observation-123",
        maximum_absolute_offset=timedelta(minutes=maximum_minutes),
    )


def test_missing_or_invalid_observation_fails_before_evidence_read():
    application, _, evidence_store = service(observation_store=Store(None))
    with pytest.raises(CloudForecastFieldObservationServiceError, match="field_observation_missing"):
        compare(application)
    assert evidence_store.loaded == []

    cause = FieldObservationPersistenceError("invalid_json_document")
    application, _, evidence_store = service(observation_store=Store(error=cause))
    with pytest.raises(CloudForecastFieldObservationServiceError, match="field_observation_invalid") as raised:
        compare(application)
    assert raised.value.__cause__ is cause
    assert evidence_store.loaded == []


def test_missing_or_invalid_decision_evidence_is_explicit():
    application, _, evidence_store = service(evidence_store=Store(None))
    with pytest.raises(CloudForecastFieldObservationServiceError, match="decision_evidence_missing"):
        compare(application)
    assert evidence_store.loaded == [{"decision_id": "decision-789"}]

    cause = DecisionForecastEvidencePersistenceError("invalid_json_document")
    application, _, _ = service(evidence_store=Store(error=cause))
    with pytest.raises(CloudForecastFieldObservationServiceError, match="decision_evidence_invalid") as raised:
        compare(application)
    assert raised.value.__cause__ is cause


def test_happy_path_uses_observation_decision_id_directly():
    source = observation(cloud_condition=CloudCondition.PARTLY_CLOUDY)
    point = cloud_point(-4, 85.0)
    application, observation_store, evidence_store = service(
        observation_store=Store(source),
        evidence_store=Store(DecisionForecastEvidence((point,))),
    )
    result = compare(application)
    assert isinstance(result, SelectedCloudForecastComparison)
    assert result.forecast_point is point
    assert result.comparison.observed_condition is source.cloud_condition
    assert observation_store.loaded == [{"observation_id": "observation-123"}]
    assert evidence_store.loaded == [{"decision_id": "decision-789"}]


def test_observation_without_cloud_and_outside_tolerance_return_none():
    application, _, _ = service(observation_store=Store(observation(cloud_condition=None)))
    assert compare(application) is None
    application, _, _ = service(
        evidence_store=Store(DecisionForecastEvidence((cloud_point(10, 85.0),)))
    )
    assert compare(application, maximum_minutes=5) is None


def test_temporal_ambiguity_propagates_without_translation():
    application, _, _ = service(
        evidence_store=Store(DecisionForecastEvidence((cloud_point(-5, 5.0), cloud_point(5, 85.0))))
    )
    with pytest.raises(ForecastTemporalSelectionError, match="ambiguous_nearest_forecast"):
        compare(application)


def test_unexpected_io_error_propagates_unchanged():
    error = OSError("observation filesystem unavailable")
    application, _, _ = service(observation_store=Store(error=error))
    with pytest.raises(OSError) as raised:
        compare(application)
    assert raised.value is error
