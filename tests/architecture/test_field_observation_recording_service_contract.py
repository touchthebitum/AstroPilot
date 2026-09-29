from datetime import datetime, timedelta, timezone

import pytest

from decision.field_observation import (
    CaptureMethod,
    CloudState,
    FieldObservation,
    ObservationProvenance,
    ObservationQuality,
    ObservationSourceType,
    ObservedAcquisition,
    ObservedConditions,
    ObservedTechnical,
)
from decision.mission.night_mission import NightMission
from decision.models.execution import Execution, ExecutionStatus
from decision.models.user_selection import UserSelection, UserSelectionSource
from decision.services.field_observation_context import (
    FieldObservationContextError,
    FieldObservationContextResolver,
)
from decision.services.field_observation_recording_service import (
    FieldObservationRecordingError,
    FieldObservationRecordingService,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.provider_reliability import (
    WeatherForecastPoint,
    WeatherLocation,
    WeatherValue,
    WeatherVariable,
)


NOW = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)


def observation(decision_id="decision-1", execution_id=None):
    return FieldObservation(
        observation_id="observation-1",
        decision_id=decision_id,
        execution_id=execution_id,
        observed_at_utc=NOW,
        recorded_at_utc=NOW,
        supersedes_observation_id=None,
        conditions=ObservedConditions(cloud_state=CloudState.CLEAR),
        acquisition=ObservedAcquisition(),
        technical=ObservedTechnical(),
        provenance=ObservationProvenance(
            source_type=ObservationSourceType.USER,
            capture_method=CaptureMethod.MANUAL,
        ),
        quality=ObservationQuality(),
    )


def evidence():
    location = WeatherLocation(46.91, 6.57, 770)
    return DecisionForecastEvidence(
        (
            WeatherForecastPoint(
                provider_id="provider",
                retrieved_at_utc=NOW,
                forecast_for_utc=NOW + timedelta(hours=1),
                requested_location=location,
                grid_location=location,
                values=(
                    WeatherValue(
                        variable=WeatherVariable.CLOUD_COVER_PERCENT,
                        value=20,
                        unit="%",
                    ),
                ),
            ),
        )
    )


def mission(decision_id="decision-1"):
    return NightMission(
        target="M31",
        confidence=0.9,
        equipment=["setup-1"],
        mission_id="mission-1",
        decision_id=decision_id,
        selection_id="selection-1",
        site_name="Buttes",
        imaging_field_id="field-1",
        acquisition_intent_id="intent-1",
    )


def selection(decision_id="decision-1"):
    return UserSelection(
        selection_id="selection-1",
        decision_id=decision_id,
        selected_catalog_key="M31",
        source=UserSelectionSource.PRIMARY_RECOMMENDATION,
        selected_at=NOW,
        selected_imaging_field_id="field-1",
        selected_acquisition_intent_id="intent-1",
    )


def execution():
    return Execution(
        execution_id="execution-1",
        mission_id="mission-1",
        status=ExecutionStatus.NOT_STARTED,
        actual_start=None,
        actual_end=None,
        actual_duration=None,
    )


def resolver(*, decision=evidence(), execution_value=None, mission_value=None):
    return FieldObservationContextResolver(
        decision_evidence_loader=lambda _: decision,
        execution_loader=lambda _: execution_value,
        mission_loader=lambda _: mission_value,
        selection_loader=lambda _: selection(),
    )


def test_decision_only_observation_resolves_without_execution():
    context = resolver().resolve(observation())
    assert context.decision_id == "decision-1"
    assert (context.latitude, context.longitude) == (46.91, 6.57)
    assert context.execution_id is None
    assert context.forecast_evidence_available is True


def test_execution_resolves_canonical_mission_selection_and_context():
    context = resolver(
        execution_value=execution(), mission_value=mission()
    ).resolve(observation(execution_id="execution-1"))
    assert context.site_name == "Buttes"
    assert context.target == "M31"
    assert context.catalog_key == "M31"
    assert context.imaging_field_id == "field-1"
    assert context.acquisition_intent_id == "intent-1"
    assert context.mission_id == "mission-1"
    assert context.execution_status is ExecutionStatus.NOT_STARTED


def test_missing_decision_and_execution_fail_closed():
    with pytest.raises(FieldObservationContextError, match="decision_not_found"):
        resolver(decision=None).resolve(observation())
    with pytest.raises(FieldObservationContextError, match="execution_not_found"):
        resolver().resolve(observation(execution_id="execution-1"))


def test_execution_mission_decision_mismatch_is_rejected():
    with pytest.raises(
        FieldObservationContextError,
        match="execution_decision_mismatch",
    ):
        resolver(
            execution_value=execution(),
            mission_value=mission(decision_id="decision-other"),
        ).resolve(observation(execution_id="execution-1"))


class ObservationStore:
    def __init__(self):
        self.saved = []

    def save(self, *, observation):
        self.saved.append(observation)
        return len(self.saved) == 1


def test_recording_service_only_resolves_and_writes_observation_store():
    store = ObservationStore()
    canonical = resolver(
        execution_value=execution(), mission_value=mission()
    )
    service = FieldObservationRecordingService(
        observation_store=store,
        context_resolver=canonical,
    )
    source = observation(execution_id="execution-1")
    result = service.record_observation(source)
    assert result.observation == source
    assert result.created is True
    assert store.saved == [source]
    assert vars(service) == {
        "observation_store": store,
        "context_resolver": canonical,
    }


def test_lineage_failure_happens_before_any_observation_write():
    store = ObservationStore()
    service = FieldObservationRecordingService(
        observation_store=store,
        context_resolver=resolver(decision=None),
    )
    with pytest.raises(FieldObservationRecordingError, match="decision_not_found"):
        service.record_observation(observation())
    assert store.saved == []
